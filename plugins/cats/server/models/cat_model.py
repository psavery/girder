from girder.models.model_base import AccessControlledModel

class CatModel(AccessControlledModel):
    def initialize(self):
        self.name = 'cat_model'
        self.ensureIndex('name')
        self.fed = False

    def feed():
        self.fed = True
        print('A cat has been fed!')
