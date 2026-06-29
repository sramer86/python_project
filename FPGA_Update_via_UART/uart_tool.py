import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

class SerialTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Python 串口调试工具")
        self.root.geometry("700x500")

        self.ser = serial.Serial()
        self.port_list = []
        self.is_open = False

        # ========== 顶部控制面板 ==========
        frame_top = ttk.Frame(root)
        frame_top.pack(pady=5, fill=tk.X)

        # 串口号
        ttk.Label(frame_top, text="串口：").grid(row=0, column=0, padx=5)
        self.cmb_port = ttk.Combobox(frame_top, width=10)
        self.cmb_port.grid(row=0, column=1, padx=5)

        # 波特率
        ttk.Label(frame_top, text="波特率：").grid(row=0, column=2, padx=5)
        self.cmb_baud = ttk.Combobox(frame_top, values=["9600", "115200", "57600", "38400"], width=10)
        self.cmb_baud.current(1)
        self.cmb_baud.grid(row=0, column=3, padx=5)

        # 按钮
        self.btn_open = ttk.Button(frame_top, text="打开串口", command=self.open_serial)
        self.btn_open.grid(row=0, column=4, padx=5)

        self.btn_close = ttk.Button(frame_top, text="关闭串口", command=self.close_serial, state=tk.DISABLED)
        self.btn_close.grid(row=0, column=5, padx=5)

        self.btn_refresh = ttk.Button(frame_top, text="刷新串口", command=self.refresh_ports)
        self.btn_refresh.grid(row=0, column=6, padx=5)

        # ========== 接收区 ==========
        ttk.Label(root, text="接收数据：").pack(anchor=tk.W, padx=5)
        self.rx_text = scrolledtext.ScrolledText(root, height=12)
        self.rx_text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

        # ========== 发送区 ==========
        frame_send = ttk.Frame(root)
        frame_send.pack(fill=tk.X, padx=5)
        ttk.Label(frame_send, text="发送：").pack(side=tk.LEFT)
        self.tx_entry = ttk.Entry(frame_send)
        self.tx_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.btn_send = ttk.Button(frame_send, text="发送", command=self.send_data)
        self.btn_send.pack(side=tk.LEFT)

        # 初始化
        self.refresh_ports()
        self.receive_loop()

    # 刷新可用串口
    def refresh_ports(self):
        self.port_list = [port.device for port in serial.tools.list_ports.comports()]
        self.cmb_port["values"] = self.port_list
        if self.port_list:
            self.cmb_port.current(0)

    # 打开串口
    def open_serial(self):
        try:
            port = self.cmb_port.get()
            baud = int(self.cmb_baud.get())
            self.ser.port = port
            self.ser.baudrate = baud
            self.ser.timeout = 0.5
            self.ser.open()

            self.is_open = True
            self.btn_open.config(state=tk.DISABLED)
            self.btn_close.config(state=tk.NORMAL)
            messagebox.showinfo("成功", f"已打开 {port}")
        except Exception as e:
            messagebox.showerror("错误", f"打开失败：{str(e)}")

    # 关闭串口
    def close_serial(self):
        if self.ser.is_open:
            self.ser.close()
        self.is_open = False
        self.btn_open.config(state=tk.NORMAL)
        self.btn_close.config(state=tk.DISABLED)

    # 发送数据
    def send_data(self):
        if not self.is_open:
            messagebox.showwarning("提示", "请先打开串口")
            return
        data = self.tx_entry.get()
        if not data:
            return
        try:
            self.ser.write((data + "\n").encode("utf-8"))
            self.rx_text.insert(tk.END, f"发送：{data}\n")
            self.rx_text.see(tk.END)
        except:
            messagebox.showerror("错误", "发送失败")

    # 循环接收数据
    def receive_loop(self):
        if self.is_open and self.ser.in_waiting > 0:
            try:
                data = self.ser.read(self.ser.in_waiting).decode("utf-8", errors="ignore")
                if data:
                    self.rx_text.insert(tk.END, f"接收：{data}")
                    self.rx_text.see(tk.END)
            except:
                pass
        self.root.after(50, self.receive_loop)

if __name__ == "__main__":
    root = tk.Tk()
    app = SerialTool(root)
    root.mainloop()