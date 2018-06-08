from girder.api import access
from girder.constants import AccessType, registerAccessFlag
from girder.api.describe import Description, autoDescribeRoute
from girder.api.rest import Resource, Prefix

class Cat(Resource):
    def __init__(self):
        super(Cat, self).__init__()
        self.resourceName = 'cat'

        self.route('GET', (), self.findCat)
        self.route('GET', (':id',), self.getCat)
        self.route('POST', (), self.createCat)
        self.route('PUT', (':id',), self.updateCat)
        self.route('DELETE', (':id',), self.deleteCat)
        self.route('PUT', (':id', 'feed'), self.feedCat)

    @access.public
    @autoDescribeRoute(
    Description('Find a cat'))
    def findCat(self, params):
        print('findCat() was called!')
        print('params is', params)

    @access.public
    @autoDescribeRoute(
    Description('Get a cat')
    .param('id', 'The cat ID', paramType='path'))
    def getCat(self, id, params):
        print('getCat() was called!')
        print('id is', id)
        print('params is', params)

    @access.public
    @autoDescribeRoute(
    Description('Create a cat'))
    def createCat(self, params):
        cat = Cat().save(body, validate=False)
        return cat

    @access.public
    @autoDescribeRoute(
    Description('Update a cat')
    .param('id', 'The cat ID', paramType='path'))
    def updateCat(self, id, params):
        print('updateCat() was called!')
        print('id is', id)
        print('params is', params)

    @access.public
    @autoDescribeRoute(
    Description('Delete a cat')
    .param('id', 'The cat ID', paramType='path'))
    def deleteCat(self, id, params):
        print('deleteCat() was called!')
        print('id is', id)
        print('params is', params)

    registerAccessFlag(key='cat.feed', name='Feed a cat',
                       description='Allows users to feed a cat')

    @access.user
    @autoDescribeRoute(
    Description('Feed a cat')
    .modelParam('id', 'The cat ID', model='cat', plugin='cats',
                 level=AccessType.WRITE, requiredFlags='cat.feed'))
    def feedCat(self, cat, params):
        print("You have fed the cats!")


def load(info):
    info['apiRoot'].cat = Cat()
    #info['apiRoot'].meow = Prefix()
    #info['apiRoot'].meow.cat = Cat()
