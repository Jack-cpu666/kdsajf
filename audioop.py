# Stub module to bypass missing audioop on Render
def __getattr__(name):
    raise NotImplementedError(f"audioop.{name} is not available in this environment")
