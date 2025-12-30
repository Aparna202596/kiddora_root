import random

# Utility function to generate a random OTP
def generate_otp(length=6):
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])
