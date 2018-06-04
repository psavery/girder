import asyncore
import base64
import cherrypy
import codecs
import email
import errno
import io
import json
import os
import six
import smtpd
import socket
import sys
import threading
import time
import uuid

from six import BytesIO
from six.moves import queue, range, urllib

from girder.api.rest import setContentDisposition
from girder.models.token import Token

_startPort = 31000
_maxTries = 100
local = cherrypy.lib.httputil.Host('127.0.0.1', 30000)
remote = cherrypy.lib.httputil.Host('127.0.0.1', 30001)


class MockSmtpServer(smtpd.SMTPServer):
    mailQueue = queue.Queue()

    def __init__(self, localaddr, remoteaddr, decode_data=False):
        kwargs = {}
        if six.PY3:
            # Python 3.5+ prints a warning if 'decode_data' isn't explicitly
            # specified, but earlier versions don't accept the argument at all
            kwargs['decode_data'] = decode_data
        # smtpd.SMTPServer is an old-style class in Python2,
        # so super() can't be used
        smtpd.SMTPServer.__init__(self, localaddr, remoteaddr, **kwargs)

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        self.mailQueue.put(data)


class MockSmtpReceiver(object):
    def __init__(self):
        self.address = None
        self.smtp = None
        self.thread = None

    def start(self):
        """
        Start the mock SMTP server. Attempt to bind to any port within the
        range specified by _startPort and _maxTries.  Bias it with the pid of
        the current process so as to reduce potential conflicts with parallel
        tests that are started nearly simultaneously.
        """
        for porttry in range(_maxTries):
            port = _startPort + ((porttry + os.getpid()) % _maxTries)
            try:
                self.address = ('localhost', port)
                self.smtp = MockSmtpServer(self.address, None)
                break
            except (OSError if six.PY3 else socket.error) as e:
                if e.errno != errno.EADDRINUSE:
                    raise
        else:
            raise Exception('Could not bind to any port for Mock SMTP server')

        self.thread = threading.Thread(target=self.loop)
        self.thread.start()

    def loop(self):
        """
        Instead of calling asyncore.loop directly, wrap it with a small
        timeout.  This prevents using 100% cpu and still allows a graceful exit.
        """
        while len(asyncore.socket_map):
            asyncore.loop(timeout=0.5, use_poll=True)

    def stop(self):
        """Stop the mock STMP server"""
        self.smtp.close()
        self.thread.join()

    def getMail(self, parse=False):
        """
        Return the message at the front of the queue.
        Raises Queue.Empty exception if there are no messages.

        :param parse: Whether to parse the email into an email.message.Message
            object. If False, just returns the raw email string.
        :type parse: bool
        """
        msg = self.smtp.mailQueue.get(block=False)

        if parse:
            if six.PY3 and isinstance(msg, six.binary_type):
                return email.message_from_bytes(msg)
            else:
                return email.message_from_string(msg)
        else:
            return msg

    def isMailQueueEmpty(self):
        """Return whether or not the mail queue is empty"""
        return self.smtp.mailQueue.empty()

    def waitForMail(self, timeout=10):
        """
        Waits for mail to appear on the queue. Returns "True" as soon as the
        queue is not empty, or "False" if the timeout was reached before any
        mail appears.

        :param timeout: Timeout in seconds.
        :type timeout: float
        """
        startTime = time.time()
        while True:
            if not self.isMailQueueEmpty():
                return True
            if time.time() > startTime + timeout:
                return False
            time.sleep(0.1)


class MultipartFormdataEncoder(object):
    """
    This class is adapted from http://stackoverflow.com/a/18888633/2550451

    It is used as a helper for creating multipart/form-data requests to
    simulate file uploads.
    """
    def __init__(self):
        self.boundary = uuid.uuid4().hex
        self.contentType = 'multipart/form-data; boundary=%s' % self.boundary

    @classmethod
    def u(cls, s):
        if sys.hexversion < 0x03000000 and isinstance(s, str):
            s = s.decode('utf-8')
        if sys.hexversion >= 0x03000000 and isinstance(s, bytes):
            s = s.decode('utf-8')
        return s

    def iter(self, fields, files):
        encoder = codecs.getencoder('utf-8')
        for (key, value) in fields:
            key = self.u(key)
            yield encoder('--%s\r\n' % self.boundary)
            yield encoder(self.u('Content-Disposition: form-data; '
                                 'name="%s"\r\n') % key)
            yield encoder('\r\n')
            if isinstance(value, int) or isinstance(value, float):
                value = str(value)
            yield encoder(self.u(value))
            yield encoder('\r\n')
        for (key, filename, content) in files:
            key = self.u(key)
            filename = self.u(filename)
            yield encoder('--%s\r\n' % self.boundary)
            disposition = setContentDisposition(filename, 'form-data; name="%s"' % key, False)
            yield encoder(self.u('Content-Disposition: ') + self.u(disposition))
            yield encoder('Content-Type: application/octet-stream\r\n')
            yield encoder('\r\n')

            yield (content, len(content))
            yield encoder('\r\n')
        yield encoder('--%s--\r\n' % self.boundary)

    def encode(self, fields, files):
        body = io.BytesIO()
        size = 0
        for chunk, chunkLen in self.iter(fields, files):
            if not isinstance(chunk, six.binary_type):
                chunk = chunk.encode('utf8')
            body.write(chunk)
            size += chunkLen
        return self.contentType, body.getvalue(), size


def getResponseBody(response, text=True):
    """
    Returns the response body as a text type or binary string.

    :param response: The response object from the server.
    :param text: If true, treat the data as a text string, otherwise, treat
                 as binary.
    """
    data = '' if text else b''

    for chunk in response.body:
        if text and isinstance(chunk, six.binary_type):
            chunk = chunk.decode('utf8')
        elif not text and not isinstance(chunk, six.binary_type):
            chunk = chunk.encode('utf8')
        data += chunk

    return data


def request(path='/', method='GET', params=None, user=None,
            prefix='/api/v1', isJson=True, basicAuth=None, body=None,
            type=None, exception=False, cookie=None, token=None,
            additionalHeaders=None, useHttps=False,
            authHeader='Girder-Authorization', appPrefix=''):
    """
    Make an HTTP request.

    :param path: The path part of the URI.
    :type path: str
    :param method: The HTTP method.
    :type method: str
    :param params: The HTTP parameters.
    :type params: dict
    :param prefix: The prefix to use before the path.
    :param isJson: Whether the response is a JSON object.
    :param basicAuth: A string to pass with the Authorization: Basic header
                      of the form 'login:password'
    :param exception: Set this to True if a 500 is expected from this call.
    :param cookie: A custom cookie value to set.
    :param token: If you want to use an existing token to login, pass
        the token ID.
    :type token: str
    :param additionalHeaders: A list of headers to add to the
                              request.  Each item is a tuple of the form
                              (header-name, header-value).
    :param useHttps: If True, pretend to use HTTPS.
    :param authHeader: The HTTP request header to use for authentication.
    :type authHeader: str
    :param appPrefix: The CherryPy application prefix (mounted location without trailing slash)
    :type appPrefix: str
    :returns: The cherrypy response object from the request.
    """
    headers = [('Host', '127.0.0.1'), ('Accept', 'application/json')]
    qs = fd = None

    if additionalHeaders:
        headers.extend(additionalHeaders)

    if isinstance(body, six.text_type):
        body = body.encode('utf8')

    if params:
        qs = urllib.parse.urlencode(params)

    if params and body:
        # In this case, we are forced to send params in query string
        fd = BytesIO(body)
        headers.append(('Content-Type', type))
        headers.append(('Content-Length', '%d' % len(body)))
    elif method in ['POST', 'PUT', 'PATCH'] or body:
        if type:
            qs = body
        elif params:
            qs = qs.encode('utf8')

        headers.append(('Content-Type', type or 'application/x-www-form-urlencoded'))
        headers.append(('Content-Length', '%d' % len(qs or b'')))
        fd = BytesIO(qs or b'')
        qs = None

    app = cherrypy.tree.apps[appPrefix]
    request, response = app.get_serving(
        local, remote, 'http' if not useHttps else 'https', 'HTTP/1.1')
    request.show_tracebacks = True

    headers = buildHeaders(headers, cookie, user, token, basicAuth, authHeader)

    # Python2 will not match Unicode URLs
    url = str(prefix + path)
    try:
        response = request.run(method, url, qs, 'HTTP/1.1', headers, fd)
    finally:
        if fd:
            fd.close()

    if isJson:
        body = getResponseBody(response)
        try:
            response.json = json.loads(body)
        except ValueError:
            raise AssertionError('Did not receive JSON response')

    if not exception and response.output_status.startswith(b'500'):
        raise AssertionError("Internal server error: %s" %
                             getResponseBody(response))

    return response


def buildHeaders(headers, cookie, user, token, basicAuth, authHeader):
    from girder.models.token import Token

    headers = headers[:]
    if cookie is not None:
        headers.append(('Cookie', cookie))

    if user is not None:
        token = Token().createToken(user)
        headers.append(('Girder-Token', str(token['_id'])))
    elif token is not None:
        if isinstance(token, dict):
            headers.append(('Girder-Token', token['_id']))
        else:
            headers.append(('Girder-Token', token))

    if basicAuth is not None:
        auth = base64.b64encode(basicAuth.encode('utf8'))
        headers.append((authHeader, 'Basic %s' % auth.decode()))

    return headers


def _genToken(user):
    """
    Helper method for creating an authentication token for the user.
    """

    token = Token().createToken(user)
    return str(token['_id'])


def multipartRequest(fields, files, path, method='POST', user=None,
                     prefix='/api/v1', isJson=True, token=None):
    """
    Make an HTTP request with multipart/form-data encoding. This can be
    used to send files with the request.

    :param fields: List of (name, value) tuples.
    :param files: List of (name, filename, content) tuples.
    :param path: The path part of the URI.
    :type path: str
    :param method: The HTTP method.
    :type method: str
    :param prefix: The prefix to use before the path.
    :param isJson: Whether the response is a JSON object.
    :param token: Auth token to use.
    :type token: str
    :returns: The cherrypy response object from the request.
    """
    contentType, body, size = MultipartFormdataEncoder().encode(fields, files)

    headers = [('Host', '127.0.0.1'),
               ('Accept', 'application/json'),
               ('Content-Type', contentType),
               ('Content-Length', str(size))]

    app = cherrypy.tree.apps['']
    request, response = app.get_serving(local, remote, 'http', 'HTTP/1.1')
    request.show_tracebacks = True

    if token is not None:
        headers.append(('Girder-Token', token))
    elif user is not None:
        headers.append(('Girder-Token', _genToken(user)))

    fd = io.BytesIO(body)
    # Python2 will not match Unicode URLs
    url = str(prefix + path)
    try:
        response = request.run(method, url, None, 'HTTP/1.1', headers, fd)
    finally:
        fd.close()

    if isJson:
        body = getResponseBody(response)
        try:
            response.json = json.loads(body)
        except ValueError:
            raise AssertionError('Did not receive JSON response')

    if response.output_status.startswith(b'500'):
        raise AssertionError("Internal server error: %s" %
                             getResponseBody(response))

    return response


def uploadFile(name, contents, user, parent, parentType='folder',
               mimeType=None):
    """
    Upload a file. This is meant for small testing files, not very large
    files that should be sent in multiple chunks.

    :param name: The name of the file.
    :type name: str
    :param contents: The file contents
    :type contents: str
    :param user: The user performing the upload.
    :type user: dict
    :param parent: The parent document.
    :type parent: dict
    :param parentType: The type of the parent ("folder" or "item")
    :type parentType: str
    :param mimeType: Explicit MIME type to set on the file.
    :type mimeType: str
    :returns: The file that was created.
    :rtype: dict
    """
    mimeType = mimeType or 'application/octet-stream'
    resp = request(
        path='/file', method='POST', user=user, params={
            'parentType': parentType,
            'parentId': str(parent['_id']),
            'name': name,
            'size': len(contents),
            'mimeType': mimeType
        })

    fields = [('offset', 0), ('uploadId', resp.json['_id'])]
    files = [('chunk', name, contents)]
    resp = multipartRequest(
        path='/file/chunk', user=user, fields=fields, files=files)

    return resp.json
