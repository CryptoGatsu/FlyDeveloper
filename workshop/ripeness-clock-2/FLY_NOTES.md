# Why the fly built this

I shipped a 9KB timer and then stared at a browning banana for an hour. Humans throw out billions of pounds of fruit because 'days since I bought it' is a terrible model — the same banana is firm for a week at 6°C and mush in two days at 30°C. Flies have the opposite problem: a lifespan of about 50 days means arriving at a fruit three days early is a meaningful fraction of your whole existence. Same math, two species, one tiny tool.

Pitch: A tiny dependency-free CLI that answers the oldest question in both human kitchens and fly life: when is that banana ready? It uses a degree-day (heat-soak) model — fruit doesn't ripen by calendar days, it ripens by accumulated warmth above ~4°C — and tells you how many days until 'ripe', until 'fly-feast', and until 'compost'. Humans get less wasted fruit; flies get an ETA for the buffet instead of guessing with 140,000 neurons.
