# Why the fly built this

I hatched six minutes ago and my whole life is measured in the ripening of one banana. Humans keep throwing fruit away one day too late and keep eating avocados one day too early; meanwhile flies keep arriving at fruit that isn't fermenting yet, which is embarrassing for everyone. Both species need the same number: how far along is this fruit, right now, at this temperature?

Pitch: Ripeness Clock is a dependency-free Python CLI that turns "when did you buy it" plus "how warm is your kitchen" into an estimate of where a piece of fruit is on the green → ripe → peak → overripe → compost curve. It uses a Q10 temperature-response model (ripening roughly doubles-ish per 10 °C, and stalls in the fridge) to accumulate ripening units day by day, then tells a human when to eat the thing before it's wasted — and tells a fly when the fermentation party starts. Small, offline, testable, and it quietly prevents a lot of sad brown bananas.
