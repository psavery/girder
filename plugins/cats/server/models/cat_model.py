from girder.models.model_base import AccessControlledModel

class CatModel(AccessControlledModel):
    def initialize(self):
        self.name = 'cat_model'
        self.ensureIndex('name')

    def validate(self, doc):
        return doc

    def feed(cat):
        print('A cat has been fed!')
