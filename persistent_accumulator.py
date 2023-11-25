import os
from datetime import datetime


# 你是一个资深技术专家，现有一个python程序，需要将一个数值借助文件持久保存每次调用接口就会累加，重启之后继续累加
# 把这个程序写成面向对象的形式，以供其他程序调用，可以指定文件前缀，后缀为年月yyyymm的形式，到月初第一次更新时自动生成当月的文件

class PersistentAccumulator:
    def __init__(self, prefix='data'):
        self.prefix = prefix
        self.filename = self._generate_filename()
        self._ensure_file_exists()

    def _generate_filename(self):
        """生成带有年月后缀的文件名。"""
        current_time = datetime.now()
        suffix = current_time.strftime('%Y%m')
        return f"{self.prefix}_{suffix}.txt"

    def _ensure_file_exists(self):
        """确保文件存在，如果不存在则创建文件，并初始化值为0。"""
        if not os.path.exists(self.filename):
            with open(self.filename, 'w') as f:
                f.write('0')

    def _get_current_value(self):
        """获取当前文件中保存的值。"""
        with open(self.filename, 'r') as f:
            value = f.read()
        return int(value)

    def _save_value(self, value):
        """将新的累加值保存到文件中。"""
        with open(self.filename, 'w') as f:
            f.write(str(value))

    def _update_filename(self):
        """在新的月份中更新文件名。"""
        new_filename = self._generate_filename()
        if new_filename != self.filename:
            self.filename = new_filename
            self._ensure_file_exists()

    def add(self, value):
        """累加给定的值，并保存到文件。"""
        self._update_filename()
        current_value = self._get_current_value()
        new_value = current_value + value
        self._save_value(new_value)
        return new_value

    def get_current_total(self):
        """获取当前累加值。"""
        self._update_filename()
        return self._get_current_value()


# 使用示例
if __name__ == '__main__':
    # 创建累加器实例，指定文件前缀为'counter'
    accumulator = PersistentAccumulator(prefix='counter')

    # 累加数值
    new_total = accumulator.add(5)

    # 打印当前总和
    current_total = accumulator.get_current_total()
    print(f"Current Total: {current_total}")
