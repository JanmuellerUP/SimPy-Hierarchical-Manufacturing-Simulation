import sys


def _input(message, input_type=str, max=None):
    while True:
        try:
            input_value = input_type(input(message))
            if max:
                if max < input_value:
                    raise Exception
            return input_value
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