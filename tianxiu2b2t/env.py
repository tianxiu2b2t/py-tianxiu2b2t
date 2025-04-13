import dotenv

class Env:
    def __init__(
        self,
    ):
        self.config = {}
        # load .env and .env.*
    
        for file in dotenv.find_dotenv():
            self.config.update(dotenv.dotenv_values(file))