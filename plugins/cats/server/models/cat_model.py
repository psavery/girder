from girder.models.model_base import AccessControlledModel

class CatModel(AccessControlledModel):
    def initialize(self):
        self.name = 'cat_model'
        self.ensureIndex('name')

    def validate(self, doc):
        return doc

    def feed(self, doc):
        doc['feed'] = True
        print('A cat has been fed!')
        self.save(doc)
