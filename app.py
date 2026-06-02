import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from io import StringIO
from datetime import date

st.set_page_config(
    page_title="LAPCOS 브랜드 대시보드",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed"
)

SHEET_ID = "1xXi56Knr6MwLS6hJ3beUYcfFshHWtHLKNqWKm8X8WFo"
SP_GID = "36826221"
TODAY = date.today().isoformat()

MONTH_NAMES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
               7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

# ── 데이터 로드 ────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch(name=None, gid=None):
    if gid:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    else:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={requests.utils.quote(name)}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.text

def read_csv(txt):
    return pd.read_csv(StringIO(txt), header=None, dtype=str).fillna("")

# ── 파싱 함수 ─────────────────────────────────────────────────────
def parse_sku_sheet(txt):
    """날짜가 헤더인 wide 포맷 → {sku: {month: value}}"""
    rows = read_csv(txt).values.tolist()
    h_idx, d_col = -1, -1
    for i, row in enumerate(rows[:8]):
        for j, c in enumerate(row):
            if len(c) == 10 and c.startswith("2026-") and c[7] == "-":
                h_idx, d_col = i, j
                break
        if h_idx >= 0:
            break
    if h_idx < 0:
        return {}
    dates = rows[h_idx][d_col:]
    result = {}
    for r in rows:
        if r is rows[h_idx]:
            continue
        name = str(r[0]).strip()
        if not name or name in ("SKU/ASIN:", "제품명", "FALSE", ""):
            continue
        mo = {}
        for i, d in enumerate(dates):
            if not d or len(d) != 10 or d > TODAY:
                continue
            try:
                v = float(r[d_col + i])
            except (ValueError, IndexError):
                continue
            if v:
                m = d[:7]
                mo[m] = mo.get(m, 0) + v
        if mo:
            if name in result:
                for m, v in mo.items():
                    result[name][m] = result[name].get(m, 0) + v
            else:
                result[name] = mo
    return result

def parse_sp(txt):
    """Wide: col[2]=Date/Spend 헤더, col[3+] 값"""
    rows = read_csv(txt).values.tolist()
    d_row, s_rows = None, []
    for row in rows:
        c2 = str(row[2]).strip() if len(row) > 2 else ""
        if c2 == "Date" and d_row is None:
            d_row = row
        elif c2 == "Spend":
            s_rows.append(row)
    if d_row is None or not s_rows:
        return {}
    # firstDi = index of first date
    fi = next((i for i, c in enumerate(d_row) if len(str(c)) == 10 and str(c).startswith("2026")), 3)
    result = {}
    for sr in s_rows:
        for i in range(fi, min(len(d_row), len(sr))):
            d = str(d_row[i]).strip()
            if len(d) != 10 or d > TODAY:
                continue
            try:
                v = float(sr[i])
            except (ValueError, TypeError):
                continue
            if v > 0:
                m = d[:7]
                result[m] = result.get(m, 0) + v
    return result

def parse_sb(txt):
    """Long: col[1]=date, col[2]=spend"""
    rows = read_csv(txt).values.tolist()
    result = {}
    for row in rows:
        d = str(row[1]).strip() if len(row) > 1 else ""
        if len(d) == 10 and d.startswith("2026") and d <= TODAY:
            try:
                v = float(row[2])
                if v > 0:
                    result[d[:7]] = result.get(d[:7], 0) + v
            except (ValueError, IndexError):
                pass
    return result

def parse_sessions(txt):
    """col[1]=Date/TotalSessions 헤더 wide 포맷"""
    rows = read_csv(txt).values.tolist()
    d_row, s_row = None, None
    for row in rows:
        c1 = str(row[1]).strip() if len(row) > 1 else ""
        if c1 == "Date" and d_row is None:
            d_row = row
        elif c1 == "TotalSessions" and s_row is None:
            s_row = row
        if d_row and s_row:
            break
    if d_row is None or s_row is None:
        return {}
    fi = next((i for i, c in enumerate(d_row) if len(str(c)) == 10 and str(c).startswith("2026")), -1)
    if fi < 0:
        return {}
    result = {}
    for i in range(fi, min(len(d_row), len(s_row))):
        d = str(d_row[i]).strip()
        if len(d) != 10 or d > TODAY:
            continue
        try:
            v = float(s_row[i])
            if v > 0:
                result[d[:7]] = result.get(d[:7], 0) + v
        except (ValueError, TypeError):
            pass
    return result

def fmt_dollar(v):
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    elif v >= 1000:
        return f"${v/1000:.1f}K"
    return f"${v:.0f}"

# ── CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container{padding-top:1rem;padding-bottom:1rem}
.metric-card{background:#1a1d27;border:1px solid #2e3347;border-radius:12px;padding:16px 18px;margin-bottom:8px}
.metric-label{font-size:10px;color:#8b90a7;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.metric-value{font-size:22px;font-weight:700;color:#e8eaf0}
.metric-sub{font-size:10px;color:#8b90a7;margin-top:3px}
.metric-hl .metric-value{color:#6c7fff}
.swot-card{border-radius:12px;padding:16px;margin-bottom:8px}
.swot-item{background:#21263a;border-radius:8px;padding:10px 12px;margin-bottom:6px;font-size:12px}
.swot-item b{color:#e8eaf0;display:block;margin-bottom:2px}
.swot-item span{color:#8b90a7;font-size:11px}
.brand-card{background:#1a1d27;border:1px solid #2e3347;border-radius:12px;padding:16px;margin-bottom:12px}
.pill{display:inline-block;font-size:10.5px;padding:3px 10px;border-radius:20px;margin:2px;background:#21263a;border:1px solid #2e3347;color:#e8eaf0}
.pill-hl{background:rgba(108,127,255,.15);border-color:#6c7fff;color:#6c7fff}
.pill-gn{background:rgba(52,211,153,.1);border-color:#34d399;color:#34d399}
.pill-yw{background:rgba(251,191,36,.1);border-color:#fbbf24;color:#fbbf24}
</style>
""", unsafe_allow_html=True)

# ── 헤더 ─────────────────────────────────────────────────────────
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("## 🌿 LAPCOS 브랜드 대시보드")
    st.caption("Amazon · 전체 SKU · 실시간 데이터")
with col_h2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("↻ 새로고침"):
        st.cache_data.clear()
        st.rerun()

# ── 탭 ──────────────────────────────────────────────────────────
tab_swot, tab_comp, tab_sales, tab_sess = st.tabs(
    ["📋 SWOT 분석", "🏆 K-브랜드 경쟁사", "📊 세일즈", "👥 세션 분석"]
)

# ═══════════════════════════════════════════════════════════════
# SWOT 탭
# ═══════════════════════════════════════════════════════════════
with tab_swot:
    st.caption("분석 대상: LAPCOS 시트마스크 | Amazon US | YTD 2026: 15,476유닛 · $281K 매출 · 21.1% ACoS")
    c1, c2 = st.columns(2)

    def swot_items(items):
        return "".join(f'<div class="swot-item"><b>{e}</b><span>{s}</span></div>' for e, s in items)

    with c1:
        st.markdown(f"""<div class="swot-card" style="border-top:3px solid #34d399;background:#1a1d27;border:1px solid #2e3347">
<p style="color:#34d399;font-weight:700;font-size:14px">💪 Strengths — 강점</p>
{swot_items([
    ("멀티채널 유통망","Amazon, CVS, Anthropologie, World Market, iHerb"),
    ("합리적 가격","5-pack $14.50 = 장당 $2.90 → 데일리 마스크 습관"),
    ("높은 평점","Amazon 평균 4.6/5★, 6,000+ 리뷰 누적"),
    ("다양한 SKU","Collagen, Honey, Charcoal, Pearl, Variety 등 10+"),
    ("K-뷰티 헤리티지","2017년 미국 런칭, Female & AAPI-founded"),
    ("Collagen 성장세","Jan 437 → May 1,653 유닛 (+278%), YTD 41.6%"),
])}
</div>""", unsafe_allow_html=True)

        st.markdown(f"""<div class="swot-card" style="border-top:3px solid #60a5fa;background:#1a1d27;border:1px solid #2e3347">
<p style="color:#60a5fa;font-weight:700;font-size:14px">🚀 Opportunities — 기회</p>
{swot_items([
    ("하이드로겔/오버나이트 포맷 진출","기존 팬층 즉시 활용 가능"),
    ("TikTok Shop 확장 (준비 중)","A10 알고리즘 외부 트래픽 우대"),
    ("Subscribe & Save 정기배송","데일리 마스크 특성 → LTV 30% 향상"),
    ("오프라인 리테일 확장","Ulta Beauty, Target 입점 기회"),
    ("성분 업그레이드 라인","Collagen Peptide, Ceramide 더마코스메틱"),
    ("K-뷰티 글로벌 수요 증가","Skincare Top 25 중 16개 K-beauty"),
])}
</div>""", unsafe_allow_html=True)

    with c2:
        st.markdown(f"""<div class="swot-card" style="border-top:3px solid #f87171;background:#1a1d27;border:1px solid #2e3347">
<p style="color:#f87171;font-weight:700;font-size:14px">⚠️ Weaknesses — 약점</p>
{swot_items([
    ("전통 시트마스크 포맷 한계","시장은 하이드로겔/오버나이트로 이동 중"),
    ("TikTok 바이럴 부재","BIODANCE·medicube 대비 SNS 화제성 낮음"),
    ("차별화 성분 스토리 부족","PDRN, Salmon DNA 등 히어로 성분 없음"),
    ("효능 체감 약하다는 리뷰","밀착도, 끈적임, 브라이트닝 미미 피드백"),
    ("리뷰 수 격차","BIODANCE 38,305개 vs LAPCOS ~6,000개"),
    ("패키징 감성 부족","선물/언박싱 경험 취약"),
])}
</div>""", unsafe_allow_html=True)

        st.markdown(f"""<div class="swot-card" style="border-top:3px solid #fbbf24;background:#1a1d27;border:1px solid #2e3347">
<p style="color:#fbbf24;font-weight:700;font-size:14px">🔥 Threats — 위협</p>
{swot_items([
    ("BIODANCE 카테고리 독주","sheet mask #1 · Beauty Top 6 · 월 100K+"),
    ("medicube 옴니채널 공세","TikTok→Amazon→Ulta, Big Spring Sale 5개"),
    ("저가 대량팩 경쟁","14-pack $8.99 제품들이 가격 민감층 흡수"),
    ("Amazon A10 알고리즘 변화","SNS 없는 브랜드 점점 불리"),
    ("신진 K-브랜드 급부상","SUNGBOON EDITOR, Anua 빠른 상승"),
    ("카테고리 리뷰 기준 상승","Top 25 평균 82,621개 (QoQ +19%)"),
])}
</div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 🎯 전략적 시사점")
    s1, s2, s3, s4 = st.columns(4)
    for col, title, color, items in [
        (s1, "SO — 강점으로 기회", "#34d399", ["Collagen + TikTok Shop → 히어로 집중 광고","멀티채널 + 오버나이트 신제품 → 업셀","AAPI 스토리 활용 TikTok 진정성 마케팅"]),
        (s2, "ST — 위협 방어", "#60a5fa", ["번들/Subscribe & Save → 가격 비교 회피","니치 성분 틈새 공략","리뷰 확보 → Top 3 클릭점유율 목표"]),
        (s3, "WO — 기회 활용", "#fbbf24", ["TikTok Shop Bio-Collagen 스토리 → 바이럴","오버나이트 신제품 → 포맷 구식 해결","외부 트래픽 → A10 수혜"]),
        (s4, "WT — 위협 최소화", "#f87171", ["프리미엄 포지셔닝 강화 필수","블루오션 성분·포맷 차별화","패키징 리뉴얼 → 선물 세트 시장"]),
    ]:
        with col:
            st.markdown(f"<p style='color:{color};font-weight:600;font-size:12px'>{title}</p>", unsafe_allow_html=True)
            for item in items:
                st.markdown(f"<p style='font-size:11px;color:#8b90a7;padding-left:10px'>→ {item}</p>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# 경쟁사 탭
# ═══════════════════════════════════════════════════════════════
with tab_comp:
    k1, k2, k3, k4 = st.columns(4)
    for col, val, label in [
        (k1,"144","경쟁 제품 수"), (k2,"6,001","주간 검색량 (2026.3)"),
        (k3,"$19","상위권 평균 가격"), (k4,"100K+","#1 브랜드 월 판매량")
    ]:
        with col:
            st.metric(label, val)

    def brand_card(rank, rank_color, name, tag, m1, m2, m3, products, format_tags, ingredients, strategy):
        cols = st.columns([1, 3, 2])
        with cols[0]:
            st.markdown(f"<div style='width:36px;height:36px;border-radius:50%;background:{rank_color};display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;color:#fff'>{rank}</div>", unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f"**{name}**")
            st.caption(tag)
        with cols[2]:
            st.markdown(f"<span style='color:#34d399;font-weight:700'>{m1}</span> 월 판매량 | {m2} 리뷰 | {m3}", unsafe_allow_html=True)

    with st.container():
        st.markdown("""<div class="brand-card">""", unsafe_allow_html=True)
        c1, c2 = st.columns([2, 3])
        with c1:
            st.markdown("**🥇 BIODANCE**")
            st.caption("Amazon sheet mask #1 · Q1 2026 Beauty #6")
            st.markdown('<span class="pill-hl pill">Bio-Collagen Real Deep Mask</span><span class="pill">Hydro Cera-nol Mask</span><br><span class="pill-gn pill">하이드로겔</span><span class="pill-gn pill">오버나이트</span>', unsafe_allow_html=True)
        with c2:
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("월 판매량", "100,000+")
            col_b.metric("리뷰 수", "38,305")
            col_c.metric("가격", "$19/4pk")
            st.caption("**TikTok 바이럴 → Amazon 전환** 교과서. 오버나이트 하이드로겔로 시장 재정의. Q1 2026 Beauty 6위.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    with st.container():
        c1, c2 = st.columns([2, 3])
        with c1:
            st.markdown("**🥈 medicube**")
            st.caption("Q1 2026 Beauty #1 · Big Spring Sale Top 10 중 5개")
            st.markdown('<span class="pill-hl pill">Collagen Overnight Wrapping Mask</span><span class="pill-hl pill">Jelly Gel (Salmon DNA)</span><br><span class="pill-gn pill">Gel-to-Peel-Off</span><span class="pill-yw pill">Ulta Beauty</span>', unsafe_allow_html=True)
        with c2:
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("월 판매량", "90,000+")
            col_b.metric("리뷰 수", "17,180")
            col_c.metric("가격", "$19/4pk")
            st.caption("**TikTok → Meta → Amazon → Ulta** 완전 연결형. 전환율 12~15% (카테고리 평균 2배).")

    st.divider()

    with st.container():
        c1, c2 = st.columns([2, 3])
        with c1:
            st.markdown("**🥉 SUNGBOON EDITOR**")
            st.caption("sheet mask #7 · 신흥 강자")
            st.markdown('<span class="pill-hl pill">Deep Collagen Overnight Mask</span><br><span class="pill-gn pill">오버나이트</span><span class="pill-hl pill">2,160,000PPB Collagen</span>', unsafe_allow_html=True)
        with c2:
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("월 판매량", "10,000+")
            col_b.metric("리뷰 수", "5,417")
            col_c.metric("가격", "$19/4pk")
            st.caption("**초고농도 Collagen 수치(PPB)** 성분 마케팅. Anti-aging + 안티포어 틈새 공략.")

    st.divider()
    st.markdown("#### 📊 카테고리 포지셔닝 비교 (2026.5)")
    comp_df = pd.DataFrame({
        "브랜드": ["BIODANCE","medicube","SUNGBOON EDITOR","🎯 LAPCOS"],
        "포맷": ["하이드로겔 오버나이트","Gel/Peel-Off","오버나이트","전통 시트마스크"],
        "가격": ["$19/4pk","$19/4pk","$19/4pk","$14.50/5pk"],
        "월 판매량": ["100K+","90K+","10K+","~3.1K"],
        "리뷰 수": [38305,17180,5417,6000],
        "TikTok": ["🔥 바이럴 주도","🔥 옴니채널","📈 성장 중","⚠️ 준비 중"],
        "채널": ["Amazon","Amazon, Ulta","Amazon","Amazon, CVS"],
    })
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════
# 세일즈 탭
# ═══════════════════════════════════════════════════════════════
with tab_sales:
    with st.spinner("구글 시트에서 데이터 불러오는 중..."):
        try:
            sc_txt = fetch("SALESCOUNT")
            st_txt = fetch("SALESTOTAL")
            sp_txt = fetch(gid=SP_GID)
            sb_txt = fetch("SBCAMPAIGN")
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")
            st.stop()

    count_data = parse_sku_sheet(sc_txt)
    total_data = parse_sku_sheet(st_txt)
    sp_data = parse_sp(sp_txt)
    sb_data = parse_sb(sb_txt)

    # 광고비 합산
    ad_spend = {}
    for m, v in sp_data.items(): ad_spend[m] = ad_spend.get(m, 0) + v
    for m, v in sb_data.items(): ad_spend[m] = ad_spend.get(m, 0) + v

    # SKU 집계
    sku_list = []
    for sku, months in total_data.items():
        rev = sum(months.values())
        units = sum(count_data.get(sku, {}).values())
        if rev > 0:
            sku_list.append({"sku": sku, "rev": rev, "units": units})
    sku_list.sort(key=lambda x: -x["rev"])

    total_rev = sum(s["rev"] for s in sku_list)
    total_units = sum(s["units"] for s in sku_list)
    total_spend = sum(ad_spend.values())
    acos = (total_spend / total_rev * 100) if total_rev > 0 else 0
    cur_month = date.today().strftime("%Y-%m")
    month_rev = sum(total_data.get(s["sku"], {}).get(cur_month, 0) for s in sku_list)

    # KPI
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("총 매출 (YTD)", fmt_dollar(total_rev), f"{len(sku_list)}개 SKU")
    k2.metric("총 판매량 (YTD)", f"{total_units:,.0f}", f"평균 ${total_rev/total_units:.2f}/unit" if total_units else "")
    k3.metric("총 광고비 (YTD)", fmt_dollar(total_spend), "SP + SB 합산")
    k4.metric("ACoS", f"{acos:.1f}%", "✅ 양호" if acos < 25 else "⚠️ 주의")
    k5.metric("이번 달 매출", fmt_dollar(month_rev), MONTH_NAMES[date.today().month])

    # 월별 집계
    all_months = [f"2026-{m:02d}" for m in range(1, 13)]
    active_months = [m for m in all_months if any(total_data.get(s["sku"], {}).get(m) for s in sku_list) or ad_spend.get(m)]
    m_rev = [sum(total_data.get(s["sku"], {}).get(m, 0) for s in sku_list) for m in active_months]
    m_spend = [ad_spend.get(m, 0) for m in active_months]
    m_labels = [MONTH_NAMES[int(m[5:])] for m in active_months]

    # 차트
    col_chart1, col_chart2 = st.columns([2, 1])
    with col_chart1:
        fig = go.Figure()
        fig.add_bar(x=m_labels, y=m_rev, name="매출", marker_color="rgba(108,127,255,.8)")
        fig.add_bar(x=m_labels, y=m_spend, name="광고비", marker_color="rgba(251,191,36,.8)")
        fig.update_layout(
            title="월별 매출 vs 광고비", barmode="group",
            paper_bgcolor="#1a1d27", plot_bgcolor="#1a1d27",
            font_color="#8b90a7", legend=dict(font=dict(color="#8b90a7")),
            margin=dict(l=10, r=10, t=40, b=10), height=280,
            yaxis=dict(tickformat="$,.0f", gridcolor="#2e3347"),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_chart2:
        top8 = sku_list[:8]
        other_rev = sum(s["rev"] for s in sku_list[8:])
        labels = [s["sku"][:20] for s in top8]
        vals = [s["rev"] for s in top8]
        if other_rev > 0:
            labels.append("기타"); vals.append(other_rev)
        fig2 = go.Figure(go.Pie(labels=labels, values=vals, hole=0.5,
            marker_colors=["#6c7fff","#34d399","#fbbf24","#f87171","#a78bfa","#60a5fa","#fb923c","#4ade80","#e879f9"]))
        fig2.update_layout(
            title="SKU별 매출 비중", paper_bgcolor="#1a1d27",
            font_color="#8b90a7", legend=dict(font=dict(size=9, color="#8b90a7")),
            margin=dict(l=10, r=10, t=40, b=10), height=280,
        )
        st.plotly_chart(fig2, use_container_width=True)

    # SKU 테이블
    st.markdown("**SKU별 매출 현황 (전체)**")
    sku_df = pd.DataFrame([{
        "#": i + 1,
        "제품명": s["sku"],
        "YTD 매출": f"${s['rev']:,.2f}",
        "YTD 판매량": f"{s['units']:,.0f}",
        "평균단가": f"${s['rev']/s['units']:.2f}" if s['units'] else "-",
        "비중": f"{s['rev']/total_rev*100:.1f}%" if total_rev else "0%",
    } for i, s in enumerate(sku_list)])
    st.dataframe(sku_df, use_container_width=True, hide_index=True)

    # 월별 요약
    st.markdown("**월별 실적 요약**")
    summary = {"구분": ["매출","광고비","ACoS"]}
    for m, rev, spend, label in zip(active_months, m_rev, m_spend, m_labels):
        a = (spend / rev * 100) if rev > 0 else 0
        summary[label] = [f"${rev:,.0f}", f"${spend:,.0f}", f"{a:.1f}%"]
    st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════
# 세션 탭
# ═══════════════════════════════════════════════════════════════
with tab_sess:
    with st.spinner("세션 데이터 로드 중..."):
        sess_data = {}
        try:
            sess_txt = fetch("session")
            sess_data = parse_sessions(sess_txt)
        except Exception:
            pass

    if not sess_data:
        st.warning("세션 데이터를 찾을 수 없어요. 구글 시트에 `session` 탭이 있는지 확인해주세요.")
    else:
        # 세션이 있는 월만
        sess_months = [m for m in active_months if sess_data.get(m)]
        s_list = [sess_data[m] for m in sess_months]
        sp_list = [ad_spend.get(m, 0) for m in sess_months]
        r_list = [sum(total_data.get(s["sku"], {}).get(m, 0) for s in sku_list) for m in sess_months]
        u_list = [sum(count_data.get(s["sku"], {}).get(m, 0) for s in sku_list) for m in sess_months]
        s_labels = [MONTH_NAMES[int(m[5:])] for m in sess_months]

        total_s = sum(s_list)
        total_u = sum(u_list)
        total_r = sum(r_list)
        total_sp = sum(sp_list)
        cvr = (total_u / total_s * 100) if total_s else 0
        rps = (total_r / total_s) if total_s else 0
        cps = (total_sp / total_s) if total_s else 0

        # 피어슨 상관계수
        import numpy as np
        corr = float(np.corrcoef(sp_list, s_list)[0, 1]) if len(sp_list) >= 2 else 0

        sk1, sk2, sk3, sk4, sk5 = st.columns(5)
        sk1.metric("총 세션 (YTD)", f"{total_s:,.0f}", f"{len(sess_months)}개월 누계")
        sk2.metric("전환율 (CVR)", f"{cvr:.2f}%", "✅ 벤치마크 달성" if cvr >= 2 else "⚠️ 평균 2~4%")
        sk3.metric("세션당 매출", f"${rps:.2f}")
        sk4.metric("세션당 광고비", f"${cps:.2f}")
        sk5.metric("광고-세션 상관도", f"{corr:.2f}", "강한 상관" if corr >= 0.7 else "중간 상관" if corr >= 0.3 else "약한 상관")

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            fig3 = go.Figure()
            fig3.add_bar(x=s_labels, y=s_list, name="세션 수", marker_color="rgba(96,165,250,.8)", yaxis="y")
            fig3.add_scatter(x=s_labels, y=sp_list, name="광고비", line_color="#fbbf24", yaxis="y2")
            fig3.update_layout(
                title="월별 세션 vs 광고비", paper_bgcolor="#1a1d27", plot_bgcolor="#1a1d27",
                font_color="#8b90a7", height=280, margin=dict(l=10,r=10,t=40,b=10),
                yaxis=dict(gridcolor="#2e3347"),
                yaxis2=dict(overlaying="y", side="right", tickformat="$,.0f"),
                legend=dict(font=dict(color="#8b90a7")),
            )
            st.plotly_chart(fig3, use_container_width=True)

        with col_s2:
            cvr_list = [u/s*100 if s else 0 for u, s in zip(u_list, s_list)]
            rps_list = [r/s if s else 0 for r, s in zip(r_list, s_list)]
            fig4 = go.Figure()
            fig4.add_scatter(x=s_labels, y=cvr_list, name="CVR(%)", line_color="#6c7fff", yaxis="y")
            fig4.add_scatter(x=s_labels, y=rps_list, name="RPS($)", line_color="#34d399", yaxis="y2")
            fig4.update_layout(
                title="CVR & 세션당 매출", paper_bgcolor="#1a1d27", plot_bgcolor="#1a1d27",
                font_color="#8b90a7", height=280, margin=dict(l=10,r=10,t=40,b=10),
                yaxis=dict(gridcolor="#2e3347", ticksuffix="%"),
                yaxis2=dict(overlaying="y", side="right", tickprefix="$"),
                legend=dict(font=dict(color="#8b90a7")),
            )
            st.plotly_chart(fig4, use_container_width=True)

        # 인사이트
        c_i, c_a = st.columns(2)
        with c_i:
            st.markdown("**📊 세션 데이터 해석**")
            st.markdown(f"- 광고-세션 상관계수 **{corr:.2f}** — {'광고비 증가가 세션 증가로 이어지는 구조' if corr>=0.7 else '광고가 세션에 일정 영향' if corr>=0.3 else '광고 외 요인(SEO, 리뷰)이 세션 주도'}")
            st.markdown(f"- 세션당 매출 **${rps:.2f}** — 방문자 1명당 창출 평균 매출")
            st.markdown(f"- CVR **{cvr:.2f}%** — 뷰티 벤치마크 2~4%; {'우수' if cvr>=4 else '달성' if cvr>=2 else '개선 여지 있음'}")
        with c_a:
            st.markdown("**💡 세션 개선 조언**")
            st.markdown(f"- {'광고 예산 증가 효과적 — 성수기 전 예산 선집행 권장' if corr>=0.7 else '유기적 세션 강화 — SEO 최적화, TikTok 트래픽 연동'}")
            st.markdown("- CVR 개선: **A+ 콘텐츠** 업그레이드, 메인 이미지 A/B 테스트")
            st.markdown("- **TikTok Shop** 트래픽 → Amazon 연결 시 세션 및 A10 랭킹 상승")
            st.markdown("- 세션당 매출 향상: **번들 상품**으로 AOV 높이기")

        # 상세 테이블
        st.markdown("**월별 세션 & 전환 상세**")
        sess_df = pd.DataFrame([{
            "월": s_labels[i],
            "세션": f"{s_list[i]:,.0f}",
            "판매량": f"{u_list[i]:,.0f}",
            "CVR": f"{(u_list[i]/s_list[i]*100 if s_list[i] else 0):.2f}%",
            "매출": f"${r_list[i]:,.0f}",
            "광고비": f"${sp_list[i]:,.0f}",
            "RPS": f"${(r_list[i]/s_list[i] if s_list[i] else 0):.2f}",
        } for i in range(len(sess_months))])
        st.dataframe(sess_df, use_container_width=True, hide_index=True)

st.caption(f"🌿 LAPCOS 브랜드 대시보드 | 마지막 업데이트: {date.today().strftime('%Y.%m.%d')}")
