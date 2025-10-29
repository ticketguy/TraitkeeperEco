from py_vapid import Vapid

def generate_vapid_keys():
    vapid = Vapid()
    vapid.generate_keys()
    private_key = vapid.private_key
    public_key = vapid.public_key
    print("VAPID Public Key:", public_key)
    print("VAPID Private Key:", private_key)

if __name__ == "__main__":
    generate_vapid_keys()