class GlobalState:
    def __init__(self):
        self.num_components = -1

    def get_num_components(self):
        return self.num_components

    def set_num_components(self, value):
        self.num_components = value

global_state = GlobalState()