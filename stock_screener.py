import streamlit as st
import akshare as ak
import pandas as pd
import requests
import json
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(page_title="尾盘选股", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")

col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.markdown(
        "<div style='background:#c0392b;color:white;font-size:28px;font-weight:900;"
        "border-radius:10px;padding:10px 16px;text-align:center;margin-top:8px;letter-spacing:4px;'>"
        "洪章</div>",
        unsafe_allow_html=True,
    )
with col_title:
    st.title("📈 尾盘选股系统")
st.caption("适用时间：每个交易日 14:30 - 15:00")

with st.sidebar:
    st.header("⚙️ 筛选参数")

    st.subheader("📊 涨幅条件")
    min_pct = st.slider("最小涨幅 (%)", 0.0, 5.0, 2.0, 0.1)
    max_pct = st.slider("最大涨幅 (%)", 1.0, 10.0, 5.0, 0.1)

    st.subheader("💹 换手率条件")
    min_turnover = st.slider("换手率 ≥ (%)", 0.5, 10.0, 3.0, 0.5)
    max_turnover = st.slider("换手率 ≤ (%)", 3.0, 20.0, 10.0, 0.5)

    st.subheader("🏦 流通市值（亿元）")
    min_mv = st.number_input("流通市值 ≥ (亿)", value=50, step=10)
    max_mv = st.number_input("流通市值 ≤ (亿)", value=200, step=10)

    st.subheader("📉 振幅条件")
    max_amplitude = st.slider("最大振幅 (%)", 3.0, 15.0, 5.0, 0.5)

    st.subheader("💰 资金流向条件")
    filter_fund = st.checkbox("主力净流入为正", value=True)
    fund_days = st.radio("统计周期", ["1天", "3天", "7天"], index=1, horizontal=True)

    run_btn = st.button("🔍 开始筛选", type="primary", use_container_width=True)

st.subheader("🌐 大盘趋势参考")

@st.cache_data(ttl=300)
def get_index_data():
    try:
        all_idx = ak.stock_zh_index_spot_sina()
        sh = all_idx[all_idx["代码"] == "sh000001"].iloc[0]
        sz = all_idx[all_idx["代码"] == "sz399001"].iloc[0]
        return sh, sz, None
    except Exception as e:
        return None, None, str(e)

with st.spinner("获取大盘数据..."):
    sh_row, sz_row, idx_err = get_index_data()

col1, col2, col3 = st.columns(3)
if idx_err:
    st.warning(f"大盘数据获取失败：{idx_err}")
else:
    try:
        sh_pct = float(sh_row["涨跌幅"])
        sz_pct = float(sz_row["涨跌幅"])
        sh_val = float(sh_row["最新价"])
        sz_val = float(sz_row["最新价"])
        trend_ok = sh_pct > 0 and sz_pct > 0
        trend_label = "✅ 上升趋势（适合尾盘选股）" if trend_ok else "⚠️ 大盘偏弱（尾盘选股需谨慎）"
        with col1:
            st.metric("上证指数", f"{sh_val:.2f}", f"{sh_pct:+.2f}%")
        with col2:
            st.metric("深证成指", f"{sz_val:.2f}", f"{sz_pct:+.2f}%")
        with col3:
            st.info(trend_label)
    except Exception as e:
        st.warning(f"大盘数据解析失败：{e}")

@st.cache_data(ttl=120)
def fetch_sina_market():
    df = ak.stock_zh_a_spot()
    df["振幅"] = (df["最高"] - df["最低"]) / df["昨收"].replace(0, float("nan")) * 100
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    return df

@st.cache_data(ttl=120)
def fetch_turnover_mv():
    all_data = []
    session = requests.Session()
    for page in range(1, 70):
        url = (
            f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
            f"/Market_Center.getHQNodeData?page={page}&num=100"
            f"&sort=changepercent&asc=0&node=hs_a&_s_r_a=page"
        )
        try:
            r = session.get(url, timeout=10)
            data = json.loads(r.text)
            if not data:
                break
            all_data.extend(data)
        except Exception:
            break
    if not all_data:
        return None, "换手率数据获取失败"
    df = pd.DataFrame(all_data)
    df["nmc"] = pd.to_numeric(df["nmc"], errors="coerce") / 10000
    df["turnoverratio"] = pd.to_numeric(df["turnoverratio"], errors="coerce")
    df["code_clean"] = df["symbol"].str.replace(r"^(sh|sz|bj)", "", regex=True)
    return df[["code_clean", "turnoverratio", "nmc"]], None

# 1天对应 f62，3天对应 f267，7天对应 f164
FUND_FIELD_MAP = {"1天": "f62", "3天": "f267", "7天": "f164"}

@st.cache_data(ttl=300)
def fetch_fund_flow(days: str):
    field = FUND_FIELD_MAP.get(days, "f267")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
        "Referer": "https://data.eastmoney.com/zjlx/list.html",
    }
    all_data = []
    session = requests.Session()
    for attempt in range(3):
        try:
            all_data = []
            for pn in range(1, 60):
                url = (
                    "https://push2.eastmoney.com/api/qt/clist/get"
                    f"?fid={field}&fs=m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23,m:1+t:4"
                    f"&fields=f12,f14,{field}&pn={pn}&pz=100&np=1&fltt=2&invt=2"
                )
                r = session.get(url, headers=headers, timeout=15)
                data = r.json()
                items = data.get("data", {}).get("diff", [])
                if not items:
                    break
                all_data.extend(items)
            if all_data:
                break
        except Exception:
            continue

    if not all_data:
        return None, "资金流向接口无法获取数据"

    df = pd.DataFrame(all_data)
    df["净流入"] = pd.to_numeric(df.get(field, pd.Series(dtype=float)), errors="coerce")
    df["code_clean"] = df["f12"].astype(str).str.zfill(6)
    return df[["code_clean", "净流入"]], None

st.subheader("📋 选股结果")

def screen_stocks(base_df, extra_df, fund_df, params):
    d = base_df.copy()
    d["代码_clean"] = d["代码"].str.replace(r"^(sh|sz|bj)", "", regex=True)
    d = d.merge(extra_df, left_on="代码_clean", right_on="code_clean", how="inner")
    d["振幅"] = pd.to_numeric(d["振幅"], errors="coerce")
    d["涨跌幅"] = pd.to_numeric(d["涨跌幅"], errors="coerce")
    d = d.dropna(subset=["涨跌幅", "turnoverratio", "nmc"])

    if fund_df is not None:
        d = d.merge(fund_df, left_on="代码_clean", right_on="code_clean", how="left")
    else:
        d["净流入"] = float("nan")

    mask = (
        (d["涨跌幅"] >= params["min_pct"]) &
        (d["涨跌幅"] <= params["max_pct"]) &
        (d["turnoverratio"] >= params["min_turnover"]) &
        (d["turnoverratio"] <= params["max_turnover"]) &
        (d["nmc"] >= params["min_mv"]) &
        (d["nmc"] <= params["max_mv"]) &
        (d["振幅"] <= params["max_amplitude"])
    )

    if params["filter_fund"] and fund_df is not None:
        mask = mask & (d["净流入"] > 0)

    result = d[mask].copy()
    fund_label = f"{params['fund_days']}主力净流入(万)"
    cols = ["代码", "名称", "最新价", "涨跌幅", "turnoverratio", "nmc", "振幅", "净流入", "成交额"]
    labels = ["股票代码", "股票名称", "最新价", "涨跌幅(%)", "换手率(%)", "流通市值(亿)", "振幅(%)", fund_label, "成交额(元)"]
    display = result[cols].copy()
    display.columns = labels
    display[fund_label] = display[fund_label] / 10000
    display = display.sort_values("涨跌幅(%)", ascending=False).reset_index(drop=True)
    display.index += 1
    return display, len(d), fund_label

if run_btn:
    params = {
        "min_pct": min_pct, "max_pct": max_pct,
        "min_turnover": min_turnover, "max_turnover": max_turnover,
        "min_mv": min_mv, "max_mv": max_mv,
        "max_amplitude": max_amplitude,
        "filter_fund": filter_fund,
        "fund_days": fund_days,
    }

    progress = st.progress(0, text="正在获取行情数据...")
    err = None
    fund_df = None
    try:
        base_df = fetch_sina_market()
        progress.progress(35, text="正在获取换手率/市值数据（约20秒）...")
        extra_df, err = fetch_turnover_mv()
        if not err:
            progress.progress(70, text=f"正在获取{fund_days}资金流向数据...")
            fund_df, fund_err = fetch_fund_flow(fund_days)
            if fund_err:
                st.warning(f"资金流向数据获取失败（{fund_err}），将跳过该条件")
                fund_df = None
        progress.progress(95, text="正在筛选...")
    except Exception as e:
        err = str(e)

    progress.progress(100, text="完成")
    progress.empty()

    if err:
        st.error(f"数据获取失败：{err}")
    elif extra_df is None:
        st.error("换手率数据为空")
    else:
        result_df, total, fund_label = screen_stocks(base_df, extra_df, fund_df, params)
        if result_df.empty:
            st.warning(f"当前条件下未找到符合要求的股票（共筛查 {total} 只），可尝试放宽条件。")
        else:
            st.success(f"✅ 共筛选出 **{len(result_df)}** 只股票（共筛查 {total} 只）")
            fmt = result_df.copy()
            for col in ["涨跌幅(%)", "换手率(%)", "振幅(%)"]:
                fmt[col] = fmt[col].map(lambda x: f"{x:.2f}")
            fmt["流通市值(亿)"] = fmt["流通市值(亿)"].map(lambda x: f"{x:.1f}")
            fmt["最新价"] = fmt["最新价"].map(lambda x: f"{x:.2f}")
            fmt[fund_label] = fmt[fund_label].map(
                lambda x: f"+{x:,.0f}" if pd.notna(x) and x > 0 else (f"{x:,.0f}" if pd.notna(x) else "-")
            )
            fmt["成交额(元)"] = fmt["成交额(元)"].map(lambda x: f"{x/1e8:.2f}亿" if pd.notna(x) else "-")
            st.dataframe(fmt, use_container_width=True, height=600)
            csv = result_df.to_csv(index=True, encoding="utf-8-sig")
            now_str = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button("⬇️ 下载结果 CSV", csv, f"尾盘选股_{now_str}.csv", "text/csv")
else:
    st.info("设置左侧筛选参数后，点击「开始筛选」按钮获取结果。")

with st.expander("📖 尾盘八步法说明"):
    st.markdown("""
| 步骤 | 条件 | 本工具是否支持 |
|------|------|------|
| 1 | 涨幅 2%-5% | ✅ 可调节 |
| 2 | 量比 > 1 | ⚠️ 数据源暂不提供，可用换手率替代 |
| 3 | 换手率 5%-10% | ✅ 可调节 |
| 4 | 流通市值 50-200亿 | ✅ 可调节 |
| 5 | 量价齐升 | ⚠️ 需人工复核 K 线 |
| 6 | 均线多头排列 | ⚠️ 需人工复核均线 |
| 7 | 分时均价线之上 | ⚠️ 需人工复核分时图 |
| 8 | 资金持续流入 | ✅ 1天/3天/7天主力净流入筛选 |

> ⚠️ **注意**：本工具仅作参考，不构成投资建议。入市有风险，操作需谨慎。
    """)
