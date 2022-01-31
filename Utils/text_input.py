import sys


def _input(message, input_type=str):
    while True:
        try:
            return input_type(input(message))
        except:
            print('That´s not a valid option!\n')
            pass


def yes_no_question(question):
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    while True:
        sys.stdout.write(question)
        choice = input().lower()
        if choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")