项目使用说明

1) 环境
- 已在项目目录创建虚拟环境：`.venv`

2) 激活虚拟环境
- PowerShell:
  .\.venv\Scripts\Activate.ps1
- CMD:
  .\.venv\Scripts\activate.bat

3) 安装依赖
- 在激活的虚拟环境中运行：
  python -m pip install -r requirements.txt

4) 在 VS Code 中
- 已将解释器指向 `.venv`（工作区设置已更新）。

5) 快速示例
- 运行脚本：
  python fundStrategy.py

6) 备注
- 全局系统 Python 由 `uv` 管理（受 PEP 668 限制），因此建议使用项目虚拟环境来安装包，避免修改受管理的系统环境。
