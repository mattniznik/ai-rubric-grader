A list in Python is an ordered collection. Each item has a position, starting at 0, and you get an item back by its index, like `scores[2]`. Lists are a good fit when the order matters or when you want to go through every item in a loop.

A dictionary stores pairs of keys and values. Instead of asking for the third item, you ask for the value under a key, like `prices["coffee"]`. Looking something up by key is fast and does not depend on where the item sits.

I would use a list for the task queue in a to-do app, because the tasks need to stay in the order they were added and I mostly loop over them from the top. I would use a dictionary for a product catalog, because I always look items up by their product code, and searching a list for a code every time would be slow and awkward.

The short version: if I care about position and order, I pick a list. If I care about finding things by a label, I pick a dictionary.
