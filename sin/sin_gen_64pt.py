import numpy as np
import matplotlib.pyplot as plt

# ===================== 配置参数 =====================
POINT_NUM = 64        # 64个点
PHASE_MIN = -np.pi/2  # 起始相位 -π/2
PHASE_MAX = np.pi/2   # 结束相位 π/2
OUT_MAX = 0x50        # 输出最大值 0x50 (80)

# ===================== 生成正弦数据 =====================
angles = np.linspace(PHASE_MIN, PHASE_MAX, POINT_NUM)
sine_vals = np.sin(angles)

# 映射到 0 ~ 0xF0
data = np.round((sine_vals + 1) / 2 * OUT_MAX).astype(np.int16)

# ===================== 输出 VHDL 格式 x"XX" =====================
print("=== 64点正弦表 (VHDL格式 x\"XX\") ===")
for i in range(0, POINT_NUM, 8):
    row = [f"x\"{val:02X}\"" for val in data[i:i+8]]
    print(", ".join(row) + ",")

# ===================== 绘制波形图 =====================
plt.figure(figsize=(10, 4))
plt.plot(range(POINT_NUM), data, 'o-', color='#2E86AB', linewidth=2, markersize=4)
plt.grid(True, alpha=0.3)
plt.title(f"64-point Sine Wave (-π/2 ~ π/2, 0~0xF0)", fontsize=14)
plt.xlabel("Address (0~63)")
plt.ylabel("Value (0~240)")
plt.ylim(-5, OUT_MAX + 5)
plt.show()