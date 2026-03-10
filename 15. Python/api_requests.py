import  requests

response = requests.get("https://gitlab.com/api/v4/users/nanuchi/projects")
print(response.json())