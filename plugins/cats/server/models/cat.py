
from girder.api.rest import Resource, Prefix
from girder.models.model_base import AccessControlledModel

class Cat(AccessControlledModel):
    def initialize(self):
        self.name = 'cat_collection'
        self.ensureIndex('name')
    def validate(self, doc):
        return doc
