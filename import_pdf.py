import argparse
import fitz  # PyMuPDF
import sqlite3
import re
import os
import database

def extract_tables_from_pdf(pdf_path, country):
    """
    尝试从标准的文本型 PDF 中提取运费阶梯并写入对应的国家数据库。
    """
    if not os.path.exists(pdf_path):
        print(f"文件不存在: {pdf_path}")
        return False

    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text("text") + "\n"
        
        if not text.strip():
            print("警告: PDF中没有检测到可提取的纯文本。这可能是一个纯图片扫描件。")
            print("如果是纯图片，需要使用 OCR (如 Tesseract) 才能自动识别。")
            return False

        # 尝试匹配常见的重量阶梯和价格格式
        # 假设格式如: "0.1 - 0.2  USD 5.1  USD 1.7"
        # 这是一个极简的正则示例，实际需要根据各国的 PDF 严格定制
        pattern = re.compile(r'([\d\.]+)\s*-\s*([\d\.]+).*?(?:USD|BRL|MXN|CLP)?\s*([\d\.]+).*?(?:USD|BRL|MXN|CLP)?\s*([\d\.]+)')
        
        matches = pattern.findall(text)
        
        if not matches:
            print("未在文本中匹配到预期的 '重量 - 重量 价格1 价格2' 格式。")
            print("原始提取文本摘要:")
            print(text[:500] + "...")
            return False

        # 清空现有的该国数据表
        conn = sqlite3.connect(database.DB_PATH)
        cursor = conn.cursor()
        table_name = f"shipping_{country}"
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.commit()
        conn.close()

        # 写入新数据
        count = 0
        for match in matches:
            weight_min = float(match[0])
            weight_max = float(match[1])
            # 根据匹配顺序，通常一个是高于阈值，一个是低于阈值
            fee_above = float(match[2])
            fee_below = float(match[3])
            
            # 为了严谨，一般较贵的运费是 fee_above
            if fee_below > fee_above:
                fee_below, fee_above = fee_above, fee_below
                
            database.insert_rate(country, weight_min, weight_max, fee_below, fee_above)
            count += 1

        print(f"成功从 {pdf_path} 中为国家 {country} 提取并写入了 {count} 条运费标准！")
        return True

    except Exception as e:
        print(f"解析 PDF 时出错: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从美客多官方PDF获取运费标准并写入数据库。")
    parser.add_argument("--country", required=True, help="关联的国家名称 (如: Mexico, Brazil, Chile)")
    parser.add_argument("--pdf", required=True, help="官方 PDF 文件的路径")
    
    args = parser.parse_args()
    extract_tables_from_pdf(args.pdf, args.country)
