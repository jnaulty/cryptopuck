import os, getpass, pyinotify, time, argparse, enum, threading, subprocess
import encrypt

class EventHandler(pyinotify.ProcessEvent):
    def __init__(self, public_key, led_manager):
        self.public_key = public_key
        self.led_manager = led_manager

    def process_IN_CREATE(self, event):
        if (os.path.isdir(event.pathname)):
            print ("New mounted volume detected: " + event.pathname)
            # Wait for the volume to be mounted and avoid permission errors
            time.sleep(1)
            self.led_manager.set_state(CryptopuckState.ENCRYPTING)
            try:
                # Encrypt the volume
                encrypt.run(event.pathname, event.pathname, self.public_key)
                # Unmount the volume
                print("Unmounting " + event.pathname)
                run_system_cmd("umount " + event.pathname)
                # Change the LED state
                self.led_manager.set_state(CryptopuckState.IDLE)
                print("Finished volume encryption: " + event.pathname)
            except Exception as e:
                print(e)
                self.led_manager.set_state(CryptopuckState.ERROR)

class CryptopuckState(enum.Enum):
    """ Cryptopuck's operational states """
    IDLE = 0
    ENCRYPTING = 1
    ERROR = 2


class RpiLed():
    def __init__(self, pin):
        """ Representation of a single LED connected to an RPi.

        Arguments:
            pin         The RPi pin with BOARD numbering
        """
        self.led_pin = pin
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(led_pin, GPIO.OUT)
        GPIO.output(led_pin, GPIO.LOW)

    def turn_on(self):
        GPIO.output(led_pin, GPIO.HIGH)

    def turn_off(self):
        GPIO.output(led_pin, GPIO.LOW)


class LedManager():
    def __init__(self, main_thread):
        """ LED Manager's constructor, sets pin up using RPi.GPIO. """
        # Monitor the main thread to stop if it has stopped
        self.main_thread = main_thread
        # Set the type of LED to use
        self.led = RpiLed(33) if getpass.getuser() == "pi" else None
        # Set the initial operational state
        self.state = CryptopuckState.IDLE

    def set_state(self, state):
        """ Set the operational state using CryptopuckState. """
        self.state = state

    def run(self):
        """ The main business logic of the LED Manager.

        Contains a blocking loop the controls the LED based on the internal
        state machine.
        """
        # If the LED type is not defined, then do nothing
        if not self.led:
            return
        # Blink the LED differently depending on the operational state
        while self.main_thread.is_alive():
            if self.state == CryptopuckState.IDLE:
                self.led.turn_on()
            elif self.state == CryptopuckState.ENCRYPTING:
                self.led.turn_on()
                time.sleep(0.2)
                self.led.turn_off()
                time.sleep(0.7)
            elif self.state == CryptopuckState.ERROR:
                self.led.turn_on()
                time.sleep(0.1)
                self.led.turn_off()
                time.sleep(0.3)


def run_system_cmd(cmd):
    """ Run system command using the shell.

    Arguments:
        cmd         The shell command to be run

    Return:
        0           Command was executed succefully
        1           Command failed during execution
    """
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                shell=True, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print("ERROR:\n\n%s" % e.output)
        return 1

    return 0


def main():
    parser_description = "Cryptopuck: Encrypt your drives on the fly"
    parser = argparse.ArgumentParser(description=parser_description)
    parser.add_argument("--public-key",
                        help="Path to the public key", required=True)
    args = parser.parse_args()

    # The mountpoint for new drives
    mountpoint = os.path.join("/media", getpass.getuser())  # Linux only

    # Setup the Led Manager
    main_thread = threading.current_thread()
    led_manager = LedManager(main_thread)
    led_thread = threading.Thread(target=led_manager.run())
    led_thread.start()

    # Setup pyInotify
    wm = pyinotify.WatchManager()  # Watch Manager
    mask = pyinotify.IN_CREATE  # watched events

    notifier = pyinotify.Notifier(wm, EventHandler(args.public_key, led_manager))
    wdd = wm.add_watch(mountpoint, mask)

    notifier.loop()  # Blocking loop
    led_thread.join()

if __name__ == "__main__":
    main()
