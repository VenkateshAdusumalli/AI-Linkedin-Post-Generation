from config.settings import validate_config
from agents.image_agent import generate_linkedin_image

config = validate_config()
print('CONFIG_OK')
image_path = generate_linkedin_image('AI agents are changing how repetitive software workflows are automated with clean modern tools and professional results.')
print('IMAGE_OK', image_path)
