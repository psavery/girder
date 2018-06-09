from girder.models.model_base import AccessControlledModel

class CatModel(AccessControlledModel):
    def initialize(self):
        self.name = 'cat_collection'
        self.ensureIndex('name')
