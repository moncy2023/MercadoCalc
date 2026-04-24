# Python 3.10+
import json
import os
import argparse
from calculator import run_calculation
import database
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="美客多利润核算系统")
templates = Jinja2Templates(directory="templates")

# ── 启动时从 config.json 读取默认参数 ──────────────────────────────
def _load_startup_config(path: str = "config.json") -> dict:
    """在模块加载时读取配置文件，失败则返回空字典（使用硬编码默认值）"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            print(f"✅ 已从 {config_path} 加载配置参数")
            return cfg
    except FileNotFoundError:
        print(f"⚠️  配置文件 {config_path} 不存在，使用默认参数")
        return {}
    except Exception as e:
        print(f"⚠️  读取配置文件出错: {e}，使用默认参数")
        return {}

_STARTUP_CONFIG = _load_startup_config()

class CalcConfig(BaseModel):
    procurement_cost: float = _STARTUP_CONFIG.get("procurement_cost", 50.0)
    packaging_fee: float = _STARTUP_CONFIG.get("packaging_fee", 2.0)
    manual_final_shipping_fee: float = _STARTUP_CONFIG.get("manual_final_shipping_fee", 0.0)
    exchange_rate_usd_to_rmb: float = _STARTUP_CONFIG.get("exchange_rate_usd_to_rmb", 7.2)
    is_above_threshold: bool = _STARTUP_CONFIG.get("is_above_threshold", True)
    commission_rate: float = _STARTUP_CONFIG.get("commission_rate", 0.15)
    loss_rate: float = _STARTUP_CONFIG.get("loss_rate", 0.02)
    target_profit_percentage: float = _STARTUP_CONFIG.get("target_profit_percentage", 0.20)
    calculation_mode: int = _STARTUP_CONFIG.get("calculation_mode", 1)
    platform_selling_price: float = _STARTUP_CONFIG.get("platform_selling_price", 100.0)
    country_for_shipping: str = _STARTUP_CONFIG.get("country_for_shipping", "Brazil")
    weight_g: float = _STARTUP_CONFIG.get("weight_g", 1000.0)
    auto_threshold: bool = _STARTUP_CONFIG.get("auto_threshold", True)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "config": _STARTUP_CONFIG}
    )

@app.get("/api/defaults")
async def api_defaults():
    """返回 config.json 中的默认参数，供前端表单初始化"""
    return _STARTUP_CONFIG

@app.post("/api/calculate")
async def api_calculate(config: CalcConfig):
    result = run_calculation(config.model_dump())
    return result

@app.get("/api/countries")
async def api_countries():
    return database.get_all_countries()

@app.get("/api/preview_shipping")
async def api_preview_shipping(
    country: str = "Mexico",
    weight_g: float = 0,
    is_above_threshold: bool = True,
    exchange_rate: float = 7.2
):
    """实时预览运费：根据国家、重量、阈值、汇率 计算最终运费(RMB)"""
    weight_kg = weight_g / 1000.0
    db_fee_usd = database.get_shipping_fee(country, weight_kg, is_above_threshold)
    db_fee_usd = db_fee_usd if db_fee_usd is not None else 0.0
    final_fee = round(db_fee_usd * exchange_rate, 2)
    return {
        "db_fee_usd": db_fee_usd,
        "final_fee": final_fee
    }

@app.get("/api/shipping_rates/{country}")
async def api_shipping_rates(country: str):
    rates = database.get_country_rates(country)
    return rates

@app.get("/api/country_metadata/{country}")
async def api_country_metadata(country: str):
    meta = database.get_country_metadata(country)
    if meta:
        return meta
    return {"local_currency": "N/A", "threshold_local": 0, "threshold_usd": 0}

@app.get("/shipping", response_class=HTMLResponse)
async def shipping_page(request: Request):
    return templates.TemplateResponse(request=request, name="shipping.html", context={"request": request})

def load_config(path="config.json"):
    """CLI 模式下从指定路径读取配置（兼容 --config 参数）"""
    abs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config file: {e}")
        return {}

def main():
    parser = argparse.ArgumentParser(description="美客多利润核算工具 (Mercado Libre Profit Calculator)")
    parser.add_argument("mode", choices=["cli", "web"], help="运行模式: cli(文本模式) 或 web(网页模式)")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--host", default="127.0.0.1", help="Web服务器监听地址")
    parser.add_argument("--port", type=int, default=9001, help="Web服务器端口")

    args = parser.parse_args()

    if args.mode == "cli":
        print("=== 运行在文本模式 (CLI Mode) ===")
        config = load_config(args.config)
        try:
            result = run_calculation(config)
            print("--- 核算结果 ---")
            for k, v in result.items():
                if 'percentage' in k:
                    print(f"{k}: {v*100:.2f}%")
                else:
                    print(f"{k}: {v}")
            print("----------------")
        except Exception as e:
            print(f"Calculation Error: {e}")
            
    elif args.mode == "web":
        print(f"=== 运行在Web模式 (Web Mode) http://{args.host}:{args.port} ===")
        uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
