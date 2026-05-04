import serial
import numpy as np
import matplotlib.pyplot as plt
import csv
import time
import sys
from datetime import datetime

PORT = "COM4"
AVERAGES = 3  # ile razy mierzyc kazdy punkt

plt.ion()
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
fig.suptitle('Live Impedance Measurement', fontsize=13)


def update_live_plot(axes, freqs, Z, phase, Rs, C):
    titles  = ['|Z| [Ω]', 'Phase [°]', 'Rs [Ω]', 'C [F]']
    colors  = ['blue', 'green', 'red', 'magenta']
    ylabels = ['|Z| [Ω]', 'Phase [°]', 'Rs [Ω]', 'C [F]']
    data    = [Z, phase, Rs, C]

    for idx, ax in enumerate(axes.flat):
        ax.cla()
        if len(freqs) > 0:
            ax.semilogx(freqs, data[idx], '-o',
                        color=colors[idx], markersize=4, linewidth=1.2)
        ax.set_title(titles[idx], fontsize=11)
        ax.set_xlabel('Frequency [Hz]')
        ax.set_ylabel(ylabels[idx])
        ax.grid(True, which='both', linestyle='--', alpha=0.5)

    plt.tight_layout()
    plt.pause(0.01)


def logspace_frequencies(start_freq, stop_freq, points):
    return np.logspace(np.log10(start_freq), np.log10(stop_freq), points)


def parse_measurement(data_line):
    try:
        z, y, phase, rs, x = map(float, data_line.strip().split(","))
        real = z * np.cos(np.radians(phase))
        imag = z * np.sin(np.radians(phase))
        return real, imag, x, z, y, phase, rs
    except Exception as e:
        print(f"Parsing error: {e} | Received data: {data_line}")
        return None, None, None, None, None, None, None


def print_progress_bar(iteration, total, length=30):
    percent = int((iteration / total) * 100)
    filled_length = int(length * iteration // total)
    bar = '#' * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r[{bar}] {percent}%')
    sys.stdout.flush()


def get_measurement(ser, retries=3):
    for attempt in range(retries):
        cmd = ":MEAS?"
        print(f"➡️ Sending: {cmd} (attempt {attempt+1})")
        ser.write(f"{cmd}\r".encode())
        time.sleep(0.3)
        response = ser.readline().decode().strip()
        print(f"⬅️ Received: {response}")
        result = parse_measurement(response)
        if result[0] is not None:
            return result
        else:
            print("⚠️ Invalid data, retrying...")
    return None, None, None, None, None, None, None


def trigger_and_wait(ser, f):
    """Wysyla trigger i czeka na zakonczenie pomiaru."""
    ser.write(f":FREQUENCY {f:.3f}\r".encode())
    time.sleep(0.2)
    ser.write("*TRG\r".encode())
    time.sleep(0.2)

    period     = 1 / f
    total_wait = period + 0.02 + 0.2
    elapsed    = 0
    step       = 0.1
    while elapsed < total_wait:
        sys.stdout.write(f"\r⏳ Pozostało: {total_wait - elapsed:.1f} s ")
        sys.stdout.flush()
        time.sleep(step)
        elapsed += step
    sys.stdout.write("\r✅ Czekanie zakończone.         \n")

    # Czekanie na ESR0 == 6
    while True:
        response = ""
        try:
            ser.write(b":ESR0?\r")
            time.sleep(0.2)
            response = ser.readline().decode().strip()
            print(f"ESR0 response: '{response}'")
            if int(response) == 6:
                print("✅ Pomiar gotowy")
                break
        except ValueError:
            print(f"⚠️ Nieprawidłowa odpowiedź: '{response}', ponawiam...")
        time.sleep(0.1)

    ser.write(b"*CLS\r")
    time.sleep(0.2)


def calculate_C_and_L(freq, X):
    omega = 2 * np.pi * freq
    C = L = None
    if X < -1e-12:
        C = -1 / (omega * X)
    elif X > 1e-12:
        L = X / omega
    else:
        C = L = 0
    return C, L


def measure_averaged(ser, f, n=AVERAGES):
    """Mierzy n razy i zwraca usrednione wartosci."""
    results = []
    for k in range(n):
        print(f"  📊 Pomiar {k+1}/{n} przy {f:.2f} Hz")
        trigger_and_wait(ser, f)
        real, imag, x, z, y, phase, rs = get_measurement(ser)
        if real is not None and z != 0:
            results.append((real, imag, x, z, y, phase, rs))
        else:
            print(f"  ⚠️ Pomiar {k+1} nieprawidłowy, pomijam.")

    if not results:
        return None, None, None, None, None, None, None

    arr = np.array(results)
    return tuple(np.mean(arr, axis=0))


def main():
    experiment_name = input("Enter experiment name: ").strip()

    while True:
        try:
            voltage_level = float(input("Enter voltage level (V, max 5.0): "))
            if 0 < voltage_level <= 5.0:
                break
            else:
                print("⚠️ Voltage must be between 0 and 5.0 V.")
        except ValueError:
            print("⚠️ Invalid input.")

    start_freq = float(input("Enter start frequency (Hz): "))
    stop_freq  = float(input("Enter stop frequency (Hz): "))
    points     = int(input("Enter number of measurement points: "))
    show_freq_labels     = input("Show frequency labels on Nyquist? (y/n): ").strip().lower() == 'y'
    show_nyquist_markers = input("Show markers on Nyquist? (y/n): ").strip().lower() == 'y'

    ser = serial.Serial(PORT, 9600, timeout=1)
    time.sleep(2)

    print("🔧 Configuring device...")
    commands = [
        ":TRIG EXT\r",
        ":PARAMETER1 Z\r",
        ":PARAMETER2 Y\r",
        ":PARAMETER3 PHASe\r",
        ":PARAMETER4 X\r",
        ":RANG:AUTO ON\r",
        ":AVER OFF\r",
        ":SPEED NORMAL\r",
        ":TRIG:DELA 0.02\r",
        ":MEAS:ITEM 7,18\r",
        ":LEV V\r"
    ]

    start_time = time.time()

    for cmd in commands:
        print(f"➡️ Sending: {cmd.strip()}")
        ser.write(cmd.encode())
        time.sleep(0.1)

    voltage_cmd = f":LEV:VOLT {voltage_level:.3f}\r"
    ser.write(voltage_cmd.encode())
    time.sleep(1)

    # Pomiar Rs przy DC (0 Hz)
    print("📡 Measuring Rs at 0.00 Hz...")
    ser.write(":FREQUENCY 0.00\r".encode())
    time.sleep(0.1)
    ser.write("*TRG\r".encode())

    wait_time = 10
    step = 0.1
    elapsed = 0
    while elapsed < wait_time:
        sys.stdout.write(f"\r⏳ Pozostało: {wait_time - elapsed:.1f} s ")
        sys.stdout.flush()
        time.sleep(step)
        elapsed += step
    sys.stdout.write("\r✅ Czekanie zakończone.         \n")

    _, _, _, _, _, _, rs_dc = get_measurement(ser)
    if rs_dc is None:
        print("❌ Failed to read Rs at 0 Hz.")
        rs_dc = "N/A"
    print(f"\nℹ️ Rs at 0 Hz: {rs_dc} [Ω]")

    freqs = logspace_frequencies(start_freq, stop_freq, points)

    real_parts, imag_parts = [], []
    magnitude, phase_deg   = [], []
    csv_data               = []

    live_freqs, live_Z, live_phase, live_Rs, live_C = [], [], [], [], []

    print(f"\n⚙️ Starting measurements (avg {AVERAGES}x per point)...")

    for i, f in enumerate(freqs):
        print(f"\n🔁 Punkt {i+1}/{points} — {f:.2f} Hz")

        real, imag, x, z, y, phase, rs = measure_averaged(ser, f, AVERAGES)

        if real is not None and z != 0:
            C, L = calculate_C_and_L(f, x)

            real_parts.append(real)
            imag_parts.append(imag)
            magnitude.append(z)
            phase_deg.append(phase)

            # CSV: tylko dane z wykresow (Z, phase, Rs, C)
            csv_data.append((
                f,
                round(z, 6),
                round(phase, 4),
                round(rs, 6),
                round(C, 12) if C is not None else "N/A",
                round(real, 6),
                round(imag, 6),
            ))

            live_freqs.append(f)
            live_Z.append(z)
            live_phase.append(phase)
            live_Rs.append(rs)
            live_C.append(C if C is not None else float('nan'))
            update_live_plot(axes, live_freqs, live_Z, live_phase, live_Rs, live_C)

        else:
            print(f"❌ Brak danych przy {f:.0f} Hz — pomijam.")

        print_progress_bar(i + 1, points)

    ser.close()

    end_time = time.time()
    elapsed  = end_time - start_time
    print(f"\n\n⏱️ Czas: {elapsed:.2f} s ({elapsed/60:.2f} min)\n")
    print("✅ Measurements complete.")

    plt.ioff()

    # Zapis CSV
    timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"{experiment_name}_{timestamp}_data.csv"
    png_filename = f"{experiment_name}_{timestamp}_nyquist.png"
    svg_filename = f"{experiment_name}_{timestamp}_nyquist.svg"

    with open(csv_filename, mode='w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "Frequency (Hz)",
            "|Z| [Ohm]",
            "Phase [deg]",
            "Rs [Ohm]",
            "C [F]",
            "Re(Z) [Ohm]",
            "Im(Z) [Ohm]",
        ])
        writer.writerows(csv_data)
    print(f"📁 Data saved to {csv_filename}")

    # Nyquist
    plt.figure(figsize=(8, 6))
    plt.plot(real_parts, -np.array(imag_parts), 'b-', label='Curve')
    if show_nyquist_markers:
        plt.plot(real_parts, -np.array(imag_parts), 'ro', label='Measurements')
    if show_freq_labels:
        for xv, yv, fq in zip(real_parts, -np.array(imag_parts), freqs[:len(real_parts)]):
            plt.text(xv, yv, f"{fq:.1f} Hz", fontsize=8, rotation=45, alpha=0.7)
    plt.xlabel('Re(Z) [Ω]')
    plt.ylabel('-Im(Z) [Ω]')
    plt.title(f'Nyquist — {experiment_name}')
    plt.grid(True)
    plt.axis('equal')
    plt.legend()
    plt.tight_layout()
    plt.savefig(png_filename, facecolor='white', bbox_inches='tight', pad_inches=0.3)
    plt.savefig(svg_filename, facecolor='white', bbox_inches='tight', pad_inches=0.3)

    print(f"\nℹ️ Rs at 0 Hz: {rs_dc} [Ω]")
    plt.show()


if __name__ == "__main__":
    main()