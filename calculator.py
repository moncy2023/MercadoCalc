# Python 3.10+
import database


def get_shipping_usd(config, override_above_threshold=None):
    """
    获取物流费 (USD)，从数据库查表或手动输入。
    返回 (shipping_usd, is_above_threshold)
    """
    country = config.get("country_for_shipping", "")
    weight_g = config.get("weight_g", 0.0)
    weight_kg = weight_g / 1000.0
    exchange_rate = config.get("exchange_rate_usd_to_rmb", 7.2)
    manual_fee = config.get("manual_final_shipping_fee", 0.0)
    is_above = override_above_threshold if override_above_threshold is not None else config.get("is_above_threshold", True)

    if manual_fee > 0:
        shipping_usd = manual_fee / exchange_rate
    else:
        shipping_usd = database.get_shipping_fee(country, weight_kg, is_above)
        shipping_usd = shipping_usd if shipping_usd is not None else 0.0

    return shipping_usd, is_above


def _calc_selling_price_for_threshold(config, is_above):
    """
    内部函数：在指定阈值假设下，按正确算法计算售价 (USD)。

    正确的美客多平台售价算法：
        平台售价 = Net Proceeds + 平台佣金 + 物流费(USD)
        Net Proceeds = 采购成本 + 打包费 + 折损(占比) + 目标净利润
        平台佣金 = 佣金率 × 平台售价
        折损 = 折损率 × 平台售价
        目标净利润 = 目标利润率 × 平台售价

    推导 (全部以 USD 为单位)：
        P = (costs_rmb / rate) + loss_rate * P + profit_rate * P + commission_rate * P + shipping_usd
        P * (1 - commission_rate - loss_rate - profit_rate) = (costs_rmb / rate) + shipping_usd
        P = ((costs_rmb / rate) + shipping_usd) / (1 - commission_rate - loss_rate - profit_rate)
    """
    procurement_cost = config.get("procurement_cost", 0.0)
    packaging_fee = config.get("packaging_fee", 2.0)
    commission_rate = config.get("commission_rate", 0.15)
    loss_rate = config.get("loss_rate", 0.02)
    exchange_rate = config.get("exchange_rate_usd_to_rmb", 7.2)
    target_profit_percentage = config.get("target_profit_percentage", 0.0)

    shipping_usd, _ = get_shipping_usd(config, override_above_threshold=is_above)

    # 固定成本 (RMB)：采购成本 + 打包费（不含物流，物流单独按 USD 计）
    fixed_cost_rmb = procurement_cost + packaging_fee
    fixed_cost_usd = fixed_cost_rmb / exchange_rate

    denominator = 1 - commission_rate - loss_rate - target_profit_percentage
    if denominator <= 0:
        raise ValueError("佣金率 + 折损率 + 目标利润率 之和不能 ≥ 100%")

    # 平台售价 (USD)
    selling_price_usd = (fixed_cost_usd + shipping_usd) / denominator
    selling_price_rmb = selling_price_usd * exchange_rate

    # 各项费用明细
    commission_fee_usd = selling_price_usd * commission_rate
    loss_cost_usd = selling_price_usd * loss_rate
    target_profit_usd = selling_price_usd * target_profit_percentage
    net_proceeds_usd = fixed_cost_usd + loss_cost_usd + target_profit_usd

    return {
        "selling_price_usd": round(selling_price_usd, 2),
        "selling_price": round(selling_price_rmb, 2),
        "fixed_cost_rmb": round(fixed_cost_rmb, 2),
        "fixed_cost_usd": round(fixed_cost_usd, 2),
        "packaging_fee": round(packaging_fee, 2),
        "shipping_fee_usd": round(shipping_usd, 2),
        "shipping_fee_rmb": round(shipping_usd * exchange_rate, 2),
        "commission_fee_usd": round(commission_fee_usd, 2),
        "commission_fee": round(commission_fee_usd * exchange_rate, 2),
        "loss_cost_usd": round(loss_cost_usd, 2),
        "loss_cost": round(loss_cost_usd * exchange_rate, 2),
        "target_profit_usd": round(target_profit_usd, 2),
        "target_profit": round(target_profit_usd * exchange_rate, 2),
        "net_proceeds_usd": round(net_proceeds_usd, 2),
        "net_proceeds": round(net_proceeds_usd * exchange_rate, 2),
        "is_above_threshold": is_above,
    }, selling_price_usd


def calculate_selling_price(config):
    """
    mode 1: 计算保本售价（目标净利润 = 0）

    算法：P = (fixed_cost_usd + shipping_usd) / (1 - commission_rate - loss_rate)
    """
    # 保本模式：目标净利润 = 0，强制覆盖 config 中的利润率
    config = dict(config)
    config["target_profit_percentage"] = 0.0

    country = config.get("country_for_shipping", "")
    exchange_rate = config.get("exchange_rate_usd_to_rmb", 7.2)
    manual_fee = config.get("manual_final_shipping_fee", 0.0)
    auto_threshold = config.get("auto_threshold", True)

    # 如果是手动运费或者用户关闭了自动判断
    if manual_fee > 0 or not auto_threshold:
        result, _ = _calc_selling_price_for_threshold(
            config, is_above=config.get("is_above_threshold", True)
        )
        return result

    # ── 自动求解阈值 ──
    meta = database.get_country_metadata(country)
    threshold_usd = meta["threshold_usd"] if meta else 0

    result_below, price_usd_below = _calc_selling_price_for_threshold(config, is_above=False)
    result_above, price_usd_above = _calc_selling_price_for_threshold(config, is_above=True)

    below_consistent = (price_usd_below < threshold_usd)
    above_consistent = (price_usd_above >= threshold_usd)

    if below_consistent and not above_consistent:
        result_below["threshold_auto"] = "below"
        result_below["threshold_note"] = f"售价 ${round(price_usd_below, 2)} < 阈值 ${threshold_usd}，自动使用低于阈值运费"
        return result_below
    elif above_consistent and not below_consistent:
        result_above["threshold_auto"] = "above"
        result_above["threshold_note"] = f"售价 ${round(price_usd_above, 2)} ≥ 阈值 ${threshold_usd}，自动使用高于阈值运费"
        return result_above
    elif below_consistent and above_consistent:
        # 两个都自洽，选择售价更低的
        if result_below["selling_price_usd"] <= result_above["selling_price_usd"]:
            result_below["threshold_auto"] = "below"
            result_below["threshold_note"] = f"两种阈值均可，选择售价更低的方案（低于阈值运费更低）"
            return result_below
        else:
            result_above["threshold_auto"] = "above"
            result_above["threshold_note"] = f"两种阈值均可，选择售价更低的方案（高于阈值）"
            return result_above
    else:
        result_above["threshold_auto"] = "conflict"
        result_above["threshold_note"] = f"⚠️ 两种假设均不自洽，建议手动确认。低于阈值售价=${round(price_usd_below,2)}，高于阈值售价=${round(price_usd_above,2)}，阈值=${threshold_usd}"
        result_above["alt_result"] = result_below
        return result_above


def calculate_profit(config):
    """
    mode 2: 已知平台售价 (USD)，计算实际利润

    算法：
        Net Proceeds = 售价 - 佣金 - 运费
        利润 = Net Proceeds - 固定成本(USD) - 折损
    """
    country = config.get("country_for_shipping", "")
    exchange_rate = config.get("exchange_rate_usd_to_rmb", 7.2)
    selling_price_usd = config.get("platform_selling_price", 0.0)
    selling_price_rmb = selling_price_usd * exchange_rate

    procurement_cost = config.get("procurement_cost", 0.0)
    packaging_fee = config.get("packaging_fee", 2.0)
    commission_rate = config.get("commission_rate", 0.15)
    loss_rate = config.get("loss_rate", 0.02)

    auto_threshold = config.get("auto_threshold", True)
    manual_fee = config.get("manual_final_shipping_fee", 0.0)

    if auto_threshold and manual_fee <= 0 and selling_price_usd > 0:
        meta = database.get_country_metadata(country)
        threshold_usd = meta["threshold_usd"] if meta else 0
        is_above = selling_price_usd >= threshold_usd
        threshold_note = f"售价 ${round(selling_price_usd, 2)} {'≥' if is_above else '<'} 阈值 ${threshold_usd}，自动使用{'高于' if is_above else '低于'}阈值运费"
    else:
        is_above = config.get("is_above_threshold", True)
        threshold_note = ""

    shipping_usd, _ = get_shipping_usd(config, override_above_threshold=is_above)

    # 固定成本 (不含物流)
    fixed_cost_rmb = procurement_cost + packaging_fee
    fixed_cost_usd = fixed_cost_rmb / exchange_rate

    # 各项费用 (USD)
    commission_fee_usd = selling_price_usd * commission_rate
    loss_cost_usd = selling_price_usd * loss_rate

    # Net Proceeds = 售价 - 佣金 - 运费
    net_proceeds_usd = selling_price_usd - commission_fee_usd - shipping_usd

    # 利润 = Net Proceeds - 固定成本(USD) - 折损
    profit_usd = net_proceeds_usd - fixed_cost_usd - loss_cost_usd
    profit_rmb = profit_usd * exchange_rate
    profit_percentage = profit_usd / selling_price_usd if selling_price_usd > 0 else 0

    result = {
        "selling_price_usd": round(selling_price_usd, 2),
        "selling_price": round(selling_price_rmb, 2),
        "fixed_cost_rmb": round(fixed_cost_rmb, 2),
        "fixed_cost_usd": round(fixed_cost_usd, 2),
        "packaging_fee": round(packaging_fee, 2),
        "shipping_fee_usd": round(shipping_usd, 2),
        "shipping_fee_rmb": round(shipping_usd * exchange_rate, 2),
        "commission_fee_usd": round(commission_fee_usd, 2),
        "commission_fee": round(commission_fee_usd * exchange_rate, 2),
        "loss_cost_usd": round(loss_cost_usd, 2),
        "loss_cost": round(loss_cost_usd * exchange_rate, 2),
        "net_proceeds_usd": round(net_proceeds_usd, 2),
        "net_proceeds": round(net_proceeds_usd * exchange_rate, 2),
        "profit_usd": round(profit_usd, 2),
        "profit": round(profit_rmb, 2),
        "profit_percentage": round(profit_percentage, 4),
        "is_above_threshold": is_above,
    }
    if threshold_note:
        result["threshold_note"] = threshold_note
    return result


def calculate_target_selling_price(config):
    """
    mode 3: 反推平台售价（已知目标利润率）

    与 mode 1 逻辑相同，但保留 target_profit_percentage 不清零。
    算法：P = (fixed_cost_usd + shipping_usd) / (1 - commission_rate - loss_rate - target_profit_rate)
    """
    country = config.get("country_for_shipping", "")
    exchange_rate = config.get("exchange_rate_usd_to_rmb", 7.2)
    manual_fee = config.get("manual_final_shipping_fee", 0.0)
    auto_threshold = config.get("auto_threshold", True)

    if manual_fee > 0 or not auto_threshold:
        result, _ = _calc_selling_price_for_threshold(
            config, is_above=config.get("is_above_threshold", True)
        )
        return result

    # ── 自动求解阈值 ──
    meta = database.get_country_metadata(country)
    threshold_usd = meta["threshold_usd"] if meta else 0

    result_below, price_usd_below = _calc_selling_price_for_threshold(config, is_above=False)
    result_above, price_usd_above = _calc_selling_price_for_threshold(config, is_above=True)

    below_consistent = (price_usd_below < threshold_usd)
    above_consistent = (price_usd_above >= threshold_usd)

    if below_consistent and not above_consistent:
        result_below["threshold_auto"] = "below"
        result_below["threshold_note"] = f"售价 ${round(price_usd_below, 2)} < 阈值 ${threshold_usd}，自动使用低于阈值运费"
        return result_below
    elif above_consistent and not below_consistent:
        result_above["threshold_auto"] = "above"
        result_above["threshold_note"] = f"售价 ${round(price_usd_above, 2)} ≥ 阈值 ${threshold_usd}，自动使用高于阈值运费"
        return result_above
    elif below_consistent and above_consistent:
        if result_below["selling_price_usd"] <= result_above["selling_price_usd"]:
            result_below["threshold_auto"] = "below"
            result_below["threshold_note"] = f"两种阈值均可，选择售价更低的方案（低于阈值运费更低）"
            return result_below
        else:
            result_above["threshold_auto"] = "above"
            result_above["threshold_note"] = f"两种阈值均可，选择售价更低的方案（高于阈值）"
            return result_above
    else:
        result_above["threshold_auto"] = "conflict"
        result_above["threshold_note"] = f"⚠️ 两种假设均不自洽，建议手动确认。低于阈值售价=${round(price_usd_below,2)}，高于阈值售价=${round(price_usd_above,2)}，阈值=${threshold_usd}"
        result_above["alt_result"] = result_below
        return result_above


def run_calculation(config):
    mode = config.get("calculation_mode", 1)
    if mode == 1:
        return calculate_selling_price(config)
    elif mode == 2:
        return calculate_profit(config)
    elif mode == 3:
        return calculate_target_selling_price(config)
    else:
        raise ValueError("Invalid calculation mode.")
