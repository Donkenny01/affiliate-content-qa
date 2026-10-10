import io
import json
import pandas as pd
import streamlit as st
from qa_engine import audit_article

st.set_page_config(page_title="Affiliate Content QA", page_icon="🔎", layout="wide")
st.title("Affiliate Content QA")
st.caption("Audit article links, Amazon tags, ASIN clues, disclosure, and link status. Flags are QA leads, not proof of product availability or link ownership.")
with st.form("audit"):
    urls = st.text_area("Article URLs — one per line", placeholder="https://example.com/best-product/", height=120)
    c1, c2 = st.columns(2)
    with c1:
        tag = st.text_input("Expected Amazon associate tag (optional)", placeholder="mytag-20")
    with c2:
        check = st.checkbox("Check live link HTTP status (slower; bot blocks possible)", value=False)
    max_check = st.number_input("Maximum unique status checks per article", min_value=1, max_value=500, value=100)
    submit = st.form_submit_button("Run QA audit", type="primary")

if submit:
    targets = list(dict.fromkeys(x.strip() for x in urls.splitlines() if x.strip()))
    if not targets:
        st.warning("Enter at least one URL.")
    elif len(targets) > 30:
        st.error("Maximum 30 articles per run to avoid overloading servers.")
    else:
        results, errors = [], []
        bar = st.progress(0)
        for i, url in enumerate(targets):
            try:
                results.append(audit_article(url, tag.strip(), check, int(max_check)))
            except Exception as exc:
                errors.append({"article_url": url, "error": str(exc)[:350]})
            bar.progress((i + 1) / len(targets))
        st.session_state["audit_results"] = results
        st.session_state["audit_errors"] = errors

results = st.session_state.get("audit_results", [])
errors = st.session_state.get("audit_errors", [])
if errors:
    st.error(f"{len(errors)} article(s) could not be scanned.")
    st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)
if results:
    summary_rows = [{"article_url": r["article_url"], **r["summary"]} for r in results]
    st.subheader("Article scorecard")
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
    link_rows = [{"article_url": r["article_url"], **l} for r in results for l in r["links"]]
    issue_rows = [{"article_url": r["article_url"], **issue} for r in results for issue in r["issues"]]
    links_df = pd.DataFrame(link_rows)
    issues_df = pd.DataFrame(issue_rows, columns=["article_url", "severity", "rule", "detail", "location", "url"])
    left, right = st.columns(2)
    with left:
        st.subheader("Issues & discrepancies")
        st.dataframe(issues_df, use_container_width=True, hide_index=True)
    with right:
        st.subheader("Complete link inventory")
        st.dataframe(links_df, use_container_width=True, hide_index=True)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Scorecard", index=False)
        links_df.to_excel(writer, sheet_name="Links", index=False)
        issues_df.to_excel(writer, sheet_name="Issues", index=False)
        if errors:
            pd.DataFrame(errors).to_excel(writer, sheet_name="Errors", index=False)
    st.download_button("Download Excel QA report", data=buffer.getvalue(), file_name="affiliate_article_qa.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("Download JSON", json.dumps({"results": results, "errors": errors}, indent=2), "affiliate_article_qa.json", mime="application/json")
