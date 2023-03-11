
from oath import OCRAChallengeResponseClient
from oath._utils import fromhex


# stopdesign
# counter = 12

# mariamiro
# counter = 45
# pin = "12345"
# ocra_key = fromhex(".....")


counter = 60
pin = "fixit1"
ocra_key = fromhex(".....")


challenge = "192823"


x = OCRAChallengeResponseClient(ocra_key, "OCRA-1:HOTP-SHA1-8:C-QN06-PSHA1")
res = x.compute_response(challenge, C=counter, P=pin)


print(counter, res)
