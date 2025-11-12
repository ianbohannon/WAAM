import sys
import re
import math

# Configurable parameters
TRIGGER_DISTANCE_MM = 1.0      # Distance threshold for fan activation
FAN_ON_TIME_MS = 200           # Fan ON duration (ms)

move_re = re.compile(r"^(G0|G1)\s+([^;]*)", re.IGNORECASE)
temperature_re = re.compile(r"^(M104|M109)", re.IGNORECASE)  # Pattern to remove temp-related commands

def extract_coords(line):
    coords = {}
    for axis in ['X', 'Y', 'E', 'F']:
        match = re.search(f"{axis}(-?\\d*\\.?\\d+)", line)
        if match:
            coords[axis] = float(match.group(1))
    return coords

def distance_xy(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def interpolate(a, b, t):
    return a + (b - a) * t

def segment_move(start, end, segments):
    """Yield interpolated positions for consistent fan pulses."""
    for i in range(1, segments + 1):
        t = i / segments
        yield {
            'X': interpolate(start['X'], end['X'], t),
            'Y': interpolate(start['Y'], end['Y'], t),
            'E': interpolate(start['E'], end['E'], t),
            'F': end.get('F', start.get('F'))
        }

def process_gcode(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    output_lines = []
    last_pos = {'X': 0.0, 'Y': 0.0, 'E': 0.0}
    accumulated_distance = 0.0

    for line in lines:
        stripped = line.strip()

        # **Skip temperature-setting commands (`M104` and `M109`)**
        if temperature_re.match(stripped):
            continue  

        if not stripped.startswith(('G0', 'G1')) or 'E' not in stripped:
            output_lines.append(line)
            coords = extract_coords(line)
            last_pos.update({k: coords[k] for k in coords})
            continue

        coords = extract_coords(stripped)
        move_type = 'G1' if 'G1' in stripped else 'G0'

        start = last_pos.copy()
        end = start.copy()
        end.update(coords)

        dist_xy = distance_xy((start['X'], start['Y']), (end['X'], end['Y']))
        extruding = end['E'] > start['E']

        if extruding:
            accumulated_distance += dist_xy

            if accumulated_distance >= TRIGGER_DISTANCE_MM:
                segments = int(accumulated_distance // TRIGGER_DISTANCE_MM)
                for seg in segment_move(start, end, segments):
                    move_line = f"{move_type} X{seg['X']:.5f} Y{seg['Y']:.5f} E{seg['E']:.5f}\n"
                    output_lines.append(move_line)
                    output_lines.append("M106 S255 ; ON\n")
                    output_lines.append(f"G4 P{FAN_ON_TIME_MS} ; Wait\n")
                    output_lines.append("M107 ; OFF\n")
                    print(f"Triggered at X{seg['X']:.2f} Y{seg['Y']:.2f}")

                    accumulated_distance -= TRIGGER_DISTANCE_MM  # Reduce distance in steps
            
            # Keep original move for accuracy
            output_lines.append(f"{move_type} X{end['X']:.5f} Y{end['Y']:.5f} E{end['E']:.5f}\n")
        else:
            output_lines.append(line)

        last_pos.update(coords)

    with open(filepath, 'w') as f:
        f.writelines(output_lines)

if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            print("Usage: python pulse_fixed_no_temp.py <gcode_file>")
            input("Press Enter to exit...")
            sys.exit(1)

        gcode_file = sys.argv[1]
        print(f"Processing G-code file: {gcode_file}")
        process_gcode(gcode_file)
        print("Done.")
        input("Press Enter to exit...")

    except Exception as e:
        print(f"Error: {e}")
        input("Press Enter to exit...")
        sys.exit(1)
