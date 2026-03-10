class User:
    def __init__(self,email,name, password,job_title):
        self.email = email
        self.name = name
        self.password = password
        self.job_title = job_title

    def change_password(self, new_password):
        self.password = new_password

    def change_job_title(self, new_job_title):
        self.job_title = new_job_title

    def getinfo(self):
        print(self.email)
        print(self.name)
        print(self.password)
        print(self.job_title)

user = User("xyz@gmail.com","Mitesh", "Abc@123", "Engineer")
user.getinfo()

