import View from 'girder/views/View';
import { SORT_ASC, SORT_DESC } from 'girder/constants';

import SortCollectionWidgetTemplate from 'girder/templates/widgets/sortCollectionWidget.pug';

import 'bootstrap/js/dropdown';

/**
 * This widget is used to provide a consistent widget for sorting
 * pages of a Collection by a choosen field.
 */
var SortCollectionWidget = View.extend({
    events: {
        'click a.g-collection-sort-link': function (event) {
            var cid = $(event.currentTarget).attr('g-sort');
            this.collection.sortField = cid;
            this.collection.fetch({}, true);
        },
        'click a.g-sort-order-button': function (event) {
            if (this.collection.sortDir === SORT_ASC) {
                this.collection.sortDir = SORT_DESC;
            } else {
                this.collection.sortDir = SORT_ASC;
            }
            this.collection.fetch({}, true);
        }
    },

    initialize: function (settings) {
        this.collection = settings.collection;
        this.fields = settings.fields;
    },

    /**
     * Do not call render() until the collection has been fetched once.
     */
    render: function () {
        this.$el.html(SortCollectionWidgetTemplate({
            collection: this.collection,
            fields: this.fields
        }));
        if (this.collection.sortDir === SORT_ASC) {
            this.$('.g-down').addClass('hide');
        } else {
            this.$('.g-up').addClass('hide');
        }
        return this;
    }
});

export default SortCollectionWidget;
