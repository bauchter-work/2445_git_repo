# 2445_git_repo
Combustion Monitoring Project
The software in this project was developed to perform combustion gas monitoring in single family detached residential homes
within the United States.  Of particular interest was CO2, CO, and pressure levels within and around the flues of 
gas domestic water heaters and non-condensing central air furnaces.  In addition to sensing around the utility room, several
low power distributed Zigbee sensors were placed on forced air ingress/egress locations such as bathroom fans, rangehoods, and 
dryer ducts.  This data reported back to the main coordinator for data aggregation.
Valves, thermocouples, a pump, an offboard CO2 sensor, and an offboard CO sensor were assembled into an enclosure for field 
deployment and monitoring.  Data was both accumulated locally on a uSD Card and copied back to a remote server hourly.

The software was written to run on the Beaglebone Black Rev. C. using a custom designed "cape" or 
daughterboard (dubbed "ECW Combustion Monitoring Board v1.0"), which provides all of the 
signal conditioning, ADC conversion, General purpose inputs and outputs, and connectors associated with 
accomplishing the task.  

Feel free to contact the authors cited below for more details around the project or to
possibly obtain the custom designed "ECW Combustion Monitoring Board" Cape for your own project purposes.

Free and Open Use LICENSE:
The MIT License (MIT)

Copyright (c) 2015 Ben Auchter (Energy Center of Wisconsin), Dan Cautley (Energy Center of Wisconsin), and Tim Chapman

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
