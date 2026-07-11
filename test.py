class FakePoint:
    def __init__(self, x, y, z):
        self.x = x; self.y = y; self.z = z

# Test what happens when features is returned
def test():
    features = [0.1, 0.2, 0.3, 0.4, 0.5]
    if features:
        print("Features evaluates to True")
    else:
        print("Features evaluates to False")

test()
