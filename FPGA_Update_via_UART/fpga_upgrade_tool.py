import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import os
import zlib
import math
import time

class FPGAUpgradeTool:
    def __init__(self, root):
        """
        FPGA串口在线升级工具类初始化方法
        
        Args:
            root (tk.Tk): Tkinter主窗口对象
        """
        # 初始化主窗口
        self.root = root
        self.root.title("FPGA 串口在线升级工具")  # 设置窗口标题
        self.root.geometry("800x600")              # 设置窗口大小
        self.root.resizable(False, False)          # 禁止窗口大小调整

        # 串口相关变量初始化
        self.ser = serial.Serial()                 # 串口对象
        self.port_list = []                        # 可用串口列表
        self.is_open = False                       # 串口是否打开标志
        self.is_upgrading = False                  # 是否正在升级标志
        self.is_reading = False                    # 是否正在回读标志
        
        # 文件与配置相关变量初始化
        self.file_path = ""                        # 烧录文件路径
        self.file_size = 0                         # 文件大小（字节）
        self.flash_start_addr = 0                  # Flash烧写起始地址
        self.flash_capacity_mbit = 4               # Flash容量（Mbit），默认4Mbit
        self.use_4b_addr = False                   # 是否使用32位地址模式
        
        # 协议帧格式定义
        self.frame_header = bytes([0x55, 0x66, 0x99, 0xAA])  # 帧头
        self.frame_tail = bytes([0xAA, 0x99, 0x66, 0x55])    # 帧尾
        
        # 初始化UI界面和刷新串口列表
        self.setup_ui()
        self.refresh_ports()

    def setup_ui(self):
        """
        初始化用户界面布局
        
        创建主窗口框架和两个标签页（升级/回读），并分别初始化各功能区域
        """
        # 创建主框架，设置内边距
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 创建笔记本（标签页容器）
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # 创建两个标签页：升级页和回读页
        upgrade_tab = ttk.Frame(notebook)
        readback_tab = ttk.Frame(notebook)
        notebook.add(upgrade_tab, text="升级")   # 添加升级标签页
        notebook.add(readback_tab, text="回读")  # 添加回读标签页

        # 初始化升级标签页的各个功能区域
        self.setup_serial_section(upgrade_tab)        # 串口配置区
        self.setup_file_section(upgrade_tab)          # 烧录文件区
        self.setup_flash_config_section(upgrade_tab)  # 烧录配置区
        self.setup_operation_section(upgrade_tab)     # 操作区
        self.setup_progress_section(upgrade_tab)      # 进度与日志区
        
        # 初始化回读标签页
        self.setup_readback_section(readback_tab)

    def setup_serial_section(self, parent):
        """
        初始化串口配置区域
        
        创建串口配置界面，包含串口号选择、波特率设置、打开/关闭/刷新按钮
        
        Args:
            parent (ttk.Frame): 父容器框架
        """
        # 创建带标题的标签框架
        frame = ttk.LabelFrame(parent, text="串口配置", padding="10")
        frame.pack(fill=tk.X, pady=5)

        # 串口号标签和下拉框
        ttk.Label(frame, text="串口号：").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.cmb_port = ttk.Combobox(frame, width=12)  # 串口号选择下拉框
        self.cmb_port.grid(row=0, column=1, padx=5)

        # 波特率标签和下拉框
        ttk.Label(frame, text="波特率：").grid(row=0, column=2, padx=5, sticky=tk.W)
        baud_rates = ["9600", "115200", "230400", "460800", "921600"]  # 常见波特率列表
        self.cmb_baud = ttk.Combobox(frame, values=baud_rates, width=12)
        self.cmb_baud.current(1)  # 默认选中115200
        self.cmb_baud.grid(row=0, column=3, padx=5)

        # 打开串口按钮
        self.btn_open = ttk.Button(frame, text="打开串口", command=self.open_serial)
        self.btn_open.grid(row=0, column=4, padx=5)

        # 关闭串口按钮（初始禁用）
        self.btn_close = ttk.Button(frame, text="关闭串口", command=self.close_serial, state=tk.DISABLED)
        self.btn_close.grid(row=0, column=5, padx=5)

        # 刷新串口列表按钮
        self.btn_refresh = ttk.Button(frame, text="刷新串口", command=self.refresh_ports)
        self.btn_refresh.grid(row=0, column=6, padx=5)

    def setup_file_section(self, parent):
        """
        初始化烧录文件选择区域
        
        创建文件选择界面，包含文件路径显示、浏览按钮和文件大小显示
        
        Args:
            parent (ttk.Frame): 父容器框架
        """
        # 创建带标题的标签框架
        frame = ttk.LabelFrame(parent, text="烧录文件", padding="10")
        frame.pack(fill=tk.X, pady=5)

        # 文件路径标签和显示框（只读）
        ttk.Label(frame, text="文件路径：").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.txt_file_path = ttk.Entry(frame, width=50, state=tk.DISABLED)  # 显示选中的文件路径
        self.txt_file_path.grid(row=0, column=1, padx=5)

        # 浏览按钮
        self.btn_browse = ttk.Button(frame, text="浏览", command=self.browse_file)  # 打开文件选择对话框
        self.btn_browse.grid(row=0, column=2, padx=5)

        # 文件大小标签和显示框（只读）
        ttk.Label(frame, text="文件大小：").grid(row=1, column=0, padx=5, sticky=tk.W)
        self.txt_file_size = ttk.Entry(frame, width=20, state=tk.DISABLED)  # 显示文件大小
        self.txt_file_size.grid(row=1, column=1, padx=5, sticky=tk.W)

    def setup_flash_config_section(self, parent):
        """
        初始化烧录配置区域
        
        创建Flash配置界面，包含起始地址输入和32位地址使能选项
        
        Args:
            parent (ttk.Frame): 父容器框架
        """
        # 创建带标题的标签框架
        frame = ttk.LabelFrame(parent, text="烧录配置", padding="10")
        frame.pack(fill=tk.X, pady=5)

        # Flash起始地址标签和输入框（十六进制）
        ttk.Label(frame, text="Flash起始地址(HEX)：").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.txt_addr = ttk.Entry(frame, width=12)
        self.txt_addr.insert(0, "00000000")  # 默认地址0x00000000
        self.txt_addr.grid(row=0, column=1, padx=5)

        # 32位地址使能复选框
        self.chk_4b_addr = ttk.Checkbutton(frame, text="32位地址使能", command=self.toggle_4b_addr)
        self.chk_4b_addr.grid(row=0, column=2, padx=10)

    def setup_operation_section(self, parent):
        """
        初始化操作按钮区域
        
        创建操作按钮界面，包含开始升级按钮
        
        Args:
            parent (ttk.Frame): 父容器框架
        """
        # 创建带标题的标签框架
        frame = ttk.LabelFrame(parent, text="操作", padding="10")
        frame.pack(fill=tk.X, pady=5)

        # 开始升级按钮（居中放大）
        self.btn_start = ttk.Button(frame, text="开始升级", command=self.start_upgrade, width=20)
        self.btn_start.pack(pady=5)  # 使用pack居中显示

    def setup_progress_section(self, parent):
        """
        初始化进度与日志显示区域
        
        创建进度显示界面，包含进度条、状态标签和日志文本框
        
        Args:
            parent (ttk.Frame): 父容器框架
        """
        # 创建带标题的标签框架
        frame = ttk.LabelFrame(parent, text="进度与日志", padding="10")
        frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # 进度条
        self.progress_bar = ttk.Progressbar(frame, orient=tk.HORIZONTAL, length=400, mode='determinate')
        self.progress_bar.pack(pady=5, fill=tk.X)
        
        # 进度状态标签
        self.progress_label = ttk.Label(frame, text="等待操作...")
        self.progress_label.pack(pady=2)

        # 日志标签和滚动文本框
        ttk.Label(frame, text="日志：").pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(frame, height=15, state=tk.DISABLED)  # 只读日志显示
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=2)

    def setup_readback_section(self, parent):
        """
        初始化回读功能区域
        
        创建回读配置界面，包含Flash容量输入、开始回读按钮、CRC32显示和进度日志
        
        Args:
            parent (ttk.Frame): 父容器框架
        """
        # 回读配置框架
        frame = ttk.LabelFrame(parent, text="回读配置", padding="10")
        frame.pack(fill=tk.X, pady=5)

        # Flash容量标签和输入框
        ttk.Label(frame, text="Flash容量(Mbit)：").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.txt_flash_cap = ttk.Entry(frame, width=10)
        self.txt_flash_cap.insert(0, "4")  # 默认4Mbit
        self.txt_flash_cap.grid(row=0, column=1, padx=5)

        # 开始回读按钮
        self.btn_start_readback = ttk.Button(frame, text="开始回读", command=self.start_readback)
        self.btn_start_readback.grid(row=0, column=2, padx=10)

        # CRC32标签和显示框（只读）
        ttk.Label(frame, text="CRC32：").grid(row=0, column=3, padx=10, sticky=tk.W)
        self.txt_crc = ttk.Entry(frame, width=16, state=tk.DISABLED)
        self.txt_crc.grid(row=0, column=4, padx=5)

        # 回读进度框架
        frame2 = ttk.LabelFrame(parent, text="回读进度", padding="10")
        frame2.pack(fill=tk.BOTH, expand=True, pady=5)

        # 回读进度条
        self.readback_progress = ttk.Progressbar(frame2, orient=tk.HORIZONTAL, length=400, mode='determinate')
        self.readback_progress.pack(pady=5, fill=tk.X)

        # 回读日志标签和滚动文本框
        ttk.Label(frame2, text="日志：").pack(anchor=tk.W)
        self.readback_log_text = scrolledtext.ScrolledText(frame2, height=15, state=tk.DISABLED)
        self.readback_log_text.pack(fill=tk.BOTH, expand=True, pady=2)

    def refresh_ports(self):
        """
        刷新可用串口列表
        
        扫描系统中可用的串口设备，并更新下拉框选项
        """
        # 获取所有可用串口
        self.port_list = [port.device for port in serial.tools.list_ports.comports()]
        # 更新下拉框选项
        self.cmb_port["values"] = self.port_list
        # 如果有可用串口，默认选中第一个
        if self.port_list:
            self.cmb_port.current(0)

    def open_serial(self):
        """
        打开串口连接
        
        从界面获取串口号和波特率，配置并打开串口连接
        成功后更新按钮状态并记录日志
        """
        try:
            # 获取串口号和波特率
            port = self.cmb_port.get()
            baud = int(self.cmb_baud.get())
            
            # 配置串口参数
            self.ser.port = port
            self.ser.baudrate = baud
            self.ser.timeout = 0.01      # 读取超时时间
            self.ser.write_timeout = 1    # 写入超时时间
            self.ser.open()               # 打开串口

            # 更新状态标志和按钮状态
            self.is_open = True
            self.btn_open.config(state=tk.DISABLED)
            self.btn_close.config(state=tk.NORMAL)
            self.log("串口已打开: {}".format(port))
        except Exception as e:
            messagebox.showerror("错误", "打开串口失败: {}".format(str(e)))

    def close_serial(self):
        """
        关闭串口连接
        
        关闭当前打开的串口，更新状态标志和按钮状态，并记录日志
        """
        # 如果串口已打开则关闭
        if self.ser.is_open:
            self.ser.close()
        
        # 更新状态标志和按钮状态
        self.is_open = False
        self.btn_open.config(state=tk.NORMAL)
        self.btn_close.config(state=tk.DISABLED)
        self.log("串口已关闭")

    def browse_file(self):
        """
        浏览并选择烧录文件
        
        打开文件选择对话框，选择.bin格式的烧录文件
        更新文件路径和文件大小显示
        """
        # 打开文件选择对话框，限制为BIN文件
        file_path = filedialog.askopenfilename(filetypes=[("BIN文件", "*.bin")])
        if file_path:
            # 更新文件路径
            self.file_path = file_path
            self.txt_file_path.config(state=tk.NORMAL)
            self.txt_file_path.delete(0, tk.END)
            self.txt_file_path.insert(0, file_path)
            self.txt_file_path.config(state=tk.DISABLED)

            # 获取并显示文件大小
            self.file_size = os.path.getsize(file_path)
            self.txt_file_size.config(state=tk.NORMAL)
            self.txt_file_size.delete(0, tk.END)
            self.txt_file_size.insert(0, "{} bytes ({:.2f} MB)".format(self.file_size, self.file_size / (1024 * 1024)))
            self.txt_file_size.config(state=tk.DISABLED)

    def toggle_4b_addr(self):
        """
        切换32位地址模式
        
        根据复选框状态发送使能/关闭4B地址命令
        若串口未打开或命令发送失败，恢复复选框状态
        """
        # 检查串口是否已打开
        if not self.is_open:
            messagebox.showwarning("提示", "请先打开串口")
            self.chk_4b_addr.state(['!selected'])
            return
        
        # 获取复选框状态
        self.use_4b_addr = self.chk_4b_addr.instate(['selected'])
        
        # 根据状态构建并发送相应命令
        if self.use_4b_addr:
            cmd = self.build_command(0xB7, [])  # 使能4B地址命令
            self.log("发送使能4B地址命令")
        else:
            cmd = self.build_command(0xE9, [])  # 关闭4B地址命令
            self.log("发送关闭4B地址命令")
        
        # 发送命令，失败则恢复状态
        if not self.send_command(cmd):
            messagebox.showerror("错误", "发送命令失败")
            self.chk_4b_addr.state(['!selected'])
            self.use_4b_addr = False

    def build_command(self, cmd, data):
        """
        构建串口命令帧
        
        根据协议格式构建完整的命令帧：帧头 + 命令 + 数据 + 校验和 + 帧尾
        
        Args:
            cmd (int): 命令字节
            data (list): 数据字节列表
        
        Returns:
            bytes: 完整的命令帧
        """
        frame = bytearray()
        frame.extend(self.frame_header)  # 添加帧头
        frame.append(cmd)                # 添加命令字节
        frame.extend(data)               # 添加数据
        
        # 计算校验和（从命令字节开始累加）
        checksum = sum(frame[4:]) & 0xFF
        frame.append(checksum)           # 添加校验和
        frame.extend(self.frame_tail)    # 添加帧尾
        
        return bytes(frame)

    def build_address_bytes(self, addr):
        """
        将地址转换为字节列表
        
        根据当前地址模式（32位/24位）将地址转换为大端序字节列表
        
        Args:
            addr (int): 地址值
        
        Returns:
            list: 地址字节列表（大端序）
        """
        if self.use_4b_addr:
            # 32位地址模式：4字节，大端序
            return [(addr >> 24) & 0xFF, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF]
        else:
            # 24位地址模式：3字节，大端序
            return [(addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF]

    def send_command(self, cmd):
        """
        发送命令并等待响应
        
        发送命令帧到串口，等待100ms内接收响应
        成功响应：连续5个0x66
        失败响应：连续5个0xEE
        支持最多5次重试
        
        Args:
            cmd (bytes): 命令帧
        
        Returns:
            bool: 成功返回True，失败或超时返回False
        """
        # 检查串口状态
        if not self.is_open or not self.ser.is_open:
            return False
        
        max_retries = 5
        for retry in range(max_retries):
            try:
                # 清空输入缓冲区
                self.ser.reset_input_buffer()
                # 发送命令
                self.ser.write(cmd)
                self.ser.flush()
                
                # 等待响应（100ms超时）
                start_time = time.time()
                response = bytearray()
                
                while time.time() - start_time < 0.1:
                    if self.ser.in_waiting > 0:
                        response.extend(self.ser.read(self.ser.in_waiting))
                        
                        # 检查响应
                        if len(response) >= 5:
                            if response[-5:] == bytes([0x66, 0x66, 0x66, 0x66, 0x66]):
                                return True  # 成功
                            elif response[-5:] == bytes([0xEE, 0xEE, 0xEE, 0xEE, 0xEE]):
                                break  # 失败，准备重试
                    time.sleep(0.001)
                
                # 超时或收到EE，继续重试
                if retry < max_retries - 1:
                    self.log(f"命令响应失败，重试 {retry + 1}/{max_retries}")
                
            except Exception as e:
                self.log("发送命令异常: {}".format(str(e)))
                if retry < max_retries - 1:
                    self.log(f"异常重试 {retry + 1}/{max_retries}")
        
        return False  # 超过最大重试次数，返回失败

    def log(self, msg):
        """
        在升级日志中添加消息
        
        添加带时间戳的日志消息到升级页面的日志文本框
        
        Args:
            msg (str): 日志消息
        """
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, "[{}] {}\n".format(time.strftime("%H:%M:%S"), msg))
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def readback_log(self, msg):
        """
        在回读日志中添加消息
        
        添加带时间戳的日志消息到回读页面的日志文本框
        
        Args:
            msg (str): 日志消息
        """
        self.readback_log_text.config(state=tk.NORMAL)
        self.readback_log_text.insert(tk.END, "[{}] {}\n".format(time.strftime("%H:%M:%S"), msg))
        self.readback_log_text.see(tk.END)
        self.readback_log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def start_upgrade(self):
        """
        开始升级流程
        
        执行完整的FPGA固件升级流程：
        1. 检查串口和文件配置
        2. 读取BIN文件
        3. 擦除Flash扇区
        4. 编程Flash
        5. 显示升级结果
        """
        # 检查串口状态
        if not self.is_open or not self.ser.is_open:
            messagebox.showwarning("提示", "请先打开串口")
            return
        
        # 检查文件是否选择
        if not self.file_path:
            messagebox.showwarning("提示", "请选择烧录文件")
            return
        
        # 解析起始地址
        try:
            self.flash_start_addr = int(self.txt_addr.get(), 16)
        except:
            messagebox.showwarning("提示", "请输入有效的十六进制地址")
            return
        
        # 检查是否正在升级
        if self.is_upgrading:
            return
        
        # 设置升级状态
        self.is_upgrading = True
        self.btn_start.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0
        self.progress_label.config(text="准备升级...")
        
        try:
            # 读取BIN文件
            with open(self.file_path, 'rb') as f:
                self.bin_data = f.read()
            
            # 记录日志
            self.log("文件读取完成，大小: {} bytes".format(len(self.bin_data)))
            self.log("Flash起始地址: 0x{:08X}".format(self.flash_start_addr))
            self.log("使用{}地址模式".format("32位" if self.use_4b_addr else "24位"))
            
            # 执行擦除和编程
            success = self.erase_sectors()
            if success:
                success = self.program_flash()
            
            # 显示结果
            if success:
                self.log("升级完成")
                messagebox.showinfo("成功", "升级完成")
            else:
                self.log("升级失败")
            
        except Exception as e:
            self.log("升级异常: {}".format(str(e)))
            messagebox.showerror("错误", "升级异常: {}".format(str(e)))
        
        # 恢复状态
        self.is_upgrading = False
        self.btn_start.config(state=tk.NORMAL)

    def erase_sectors(self):
        """
        擦除Flash扇区
        
        根据BIN文件大小计算需要擦除的4KB扇区数量，逐个擦除
        每次擦除前先发送写使能命令，然后发送擦除命令
        
        Returns:
            bool: 成功返回True，失败返回False
        """
        # 计算扇区数量（向上取整）
        sector_count = math.ceil(len(self.bin_data) / 4096)
        self.log("需要擦除 {} 个4KB扇区".format(sector_count))
        
        # 初始化进度条
        self.progress_label.config(text="正在擦除...")
        self.progress_bar['maximum'] = sector_count
        self.progress_bar['value'] = 0
        
        # 逐个擦除扇区
        for i in range(sector_count):
            addr = self.flash_start_addr + i * 4096
            
            # 发送写使能命令
            if not self.send_command(self.build_command(0x06, [])):
                self.log("写使能失败，地址: 0x{:08X}".format(addr))
                return False
            
            # 发送擦除4KB扇区命令
            addr_bytes = self.build_address_bytes(addr)
            erase_cmd = self.build_command(0x20, addr_bytes)
            if not self.send_command(erase_cmd):
                self.log("擦除扇区失败，地址: 0x{:08X}".format(addr))
                return False
            
            # 更新进度
            self.progress_bar['value'] = i + 1
            self.progress_label.config(text="正在擦除... {}/{}".format(i + 1, sector_count))
            self.root.update_idletasks()
        
        self.log("扇区擦除完成")
        return True

    def program_flash(self):
        data = self.bin_data
        total_size = len(data)
        offset = 0
        
        self.progress_bar['maximum'] = total_size
        self.progress_bar['value'] = 0
        self.progress_label.config(text="正在编程...")
        
        while offset < total_size:
            chunk = data[offset:offset + 256]
            addr = self.flash_start_addr + offset
            
            if not self.send_command(self.build_command(0x06, [])):
                self.log("写使能失败，地址: 0x{:08X}".format(addr))
                return False
            
            addr_bytes = self.build_address_bytes(addr)
            program_cmd = self.build_command(0x02, addr_bytes + list(chunk))
            if not self.send_command(program_cmd):
                self.log("页编程失败，地址: 0x{:08X}".format(addr))
                return False
            
            offset += len(chunk)
            self.progress_bar['value'] = offset
            percent = int((offset / total_size) * 100)
            self.progress_label.config(text="正在编程... {}% ({}/{})".format(percent, offset, total_size))
            self.root.update_idletasks()
        
        self.log("编程完成")
        return True

    def start_readback(self):
        if not self.is_open or not self.ser.is_open:
            messagebox.showwarning("提示", "请先打开串口")
            return
        
        try:
            self.flash_capacity_mbit = int(self.txt_flash_cap.get())
        except:
            messagebox.showwarning("提示", "请输入有效的Flash容量")
            return
        
        if self.is_reading:
            return
        
        self.is_reading = True
        self.btn_start_readback.config(state=tk.DISABLED)
        self.readback_progress['value'] = 0
        
        try:
            total_bytes = (self.flash_capacity_mbit * 1024 * 1024) // 8
            read_count = total_bytes // 256
            
            self.readback_log("开始回读Flash，容量: {} Mbit = {} bytes".format(self.flash_capacity_mbit, total_bytes))
            self.readback_log("需要读取 {} 次".format(read_count))
            
            self.readback_progress['maximum'] = read_count
            
            all_data = bytearray()
            addr = 0
            success = True
            
            for i in range(read_count):
                retry = 0
                while retry < 10:
                    addr_bytes = self.build_address_bytes(addr)
                    read_cmd = self.build_command(0x03, addr_bytes)
                    
                    if not self.send_read_command(read_cmd):
                        retry += 1
                        self.readback_log("读取失败，重试 {}/10，地址: 0x{:08X}".format(retry, addr))
                        if retry >= 10:
                            self.readback_log("读取失败超过10次，退出")
                            success = False
                            break
                    else:
                        try:
                            response = self.read_response()
                            if response:
                                data = response[4:260]
                                checksum = response[260]
                                calc_checksum = sum(data) & 0xFF
                                
                                if checksum == calc_checksum:
                                    all_data.extend(data)
                                    break
                                else:
                                    retry += 1
                                    self.readback_log("校验和错误，重试 {}/10，地址: 0x{:08X}".format(retry, addr))
                                    if retry >= 10:
                                        self.readback_log("校验和错误超过10次，退出")
                                        success = False
                                        break
                            else:
                                retry += 1
                                self.readback_log("无响应，重试 {}/10，地址: 0x{:08X}".format(retry, addr))
                                if retry >= 10:
                                    self.readback_log("无响应超过10次，退出")
                                    success = False
                                    break
                        except Exception as e:
                            retry += 1
                            self.readback_log("读取异常: {}".format(str(e)))
                
                if not success:
                    break
                
                addr += 256
                self.readback_progress['value'] = i + 1
                percent = int((i + 1) / read_count * 100)
                self.root.update_idletasks()
            
            if success:
                save_path = filedialog.asksaveasfilename(defaultextension=".bin", filetypes=[("BIN文件", "*.bin")])
                if save_path:
                    with open(save_path, 'wb') as f:
                        f.write(all_data)
                    
                    crc32 = zlib.crc32(all_data) & 0xFFFFFFFF
                    self.txt_crc.config(state=tk.NORMAL)
                    self.txt_crc.delete(0, tk.END)
                    self.txt_crc.insert(0, "{:08X}".format(crc32))
                    self.txt_crc.config(state=tk.DISABLED)
                    
                    self.readback_log("回读完成，保存文件: {}".format(save_path))
                    self.readback_log("CRC32: {:08X}".format(crc32))
                    messagebox.showinfo("成功", "回读完成\nCRC32: {:08X}".format(crc32))
        
        except Exception as e:
            self.readback_log("回读异常: {}".format(str(e)))
            messagebox.showerror("错误", "回读异常: {}".format(str(e)))
        
        self.is_reading = False
        self.btn_start_readback.config(state=tk.NORMAL)

    def send_read_command(self, cmd):
        if not self.is_open or not self.ser.is_open:
            return False
        
        try:
            self.ser.reset_input_buffer()
            self.ser.write(cmd)
            self.ser.flush()
            return True
        except Exception as e:
            return False

    def read_response(self):
        start_time = time.time()
        response = bytearray()
        
        while time.time() - start_time < 0.1:
            if self.ser.in_waiting > 0:
                response.extend(self.ser.read(self.ser.in_waiting))
                if len(response) >= 265:
                    if response[:4] == self.frame_header and response[-4:] == self.frame_tail:
                        return response
            time.sleep(0.001)
        
        return None

if __name__ == "__main__":
    root = tk.Tk()
    app = FPGAUpgradeTool(root)
    root.mainloop()