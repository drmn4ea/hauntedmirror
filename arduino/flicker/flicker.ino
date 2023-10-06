/*
 * LED Flicker/control script for haunted mirror.
 * Pretty basic, but it works. This appears as a serial (USB) port for control by the host system.
 * Send one of three control characters to set the LED state:
 * * 'L': Lit
 * * 'F': Flicker
 * * 'D': Dark
 * 
 * Check your board's documentation for pinout and serial port name(s) available. 'SerialUSB' for RedBoard Turbo, 'Serial' for bog-standard Arduinos, 'Serial1'...etc. if multiple HW ports available.
 */

// Global configuration values
int g_baudrate = 115200;
int g_pwmPin = 3;
// Max and min values for fade/flicker effect; adjust for desired LED brightness range (0 ~ 255)
int g_fade_max = 255; // Reduce for lower max brightness / heat dissipation
int g_fade_min = 64;

// Initial values
int g_currentFadeValue = g_fade_max;
int g_targetFadeValue = g_fade_max;
char g_inByte=0x00;

void resetFade()
{
  g_currentFadeValue = g_fade_max;
  g_targetFadeValue = g_fade_max;
}

void updateFade()
{
  // Track toward a target fade value. If we reach it, randomly select a new value.
  if(g_currentFadeValue == g_targetFadeValue)
  {
    g_targetFadeValue = random(g_fade_min, g_fade_max);
  }
  else if(g_currentFadeValue > g_targetFadeValue)
  {
    g_currentFadeValue--;
  }
  else
  {
    g_currentFadeValue++;
  }
}

void setup() {
  // Cheesy way to show we are running... extremely dim LED
  analogWrite(g_pwmPin, 1);
  // start serial port
  SerialUSB.begin(g_baudrate);
  // Dim LED - waiting for host to connect (if detectable)
  analogWrite(g_pwmPin, 16);
  while (!SerialUSB) {
    ; // wait for serial port to connect. Needed for native USB port only
  }
}

void loop() {

  // Always step the fade value
  updateFade();
  delay(1);
  
  // check for cmd from the PC. If we didn't get one, retain the previous g_inByte value.
  if (SerialUSB.available() > 0) 
  {
    g_inByte = SerialUSB.read();
    // HACK: Always reset fade value on host command in case it switches us to fade: smoother transition
    resetFade();
  }
  
  switch(g_inByte)
  {
    case 'D': // Dark
      analogWrite(g_pwmPin, 0);
      break;
    case 'F': // Fade
      analogWrite(g_pwmPin, g_currentFadeValue);
      break;
    case 'L': // Light
    default:
      analogWrite(g_pwmPin, g_fade_max);
      break;
  }

}
