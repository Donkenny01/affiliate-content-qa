from qa_engine import audit_html


def test_draft_links_and_tags():
    html = '<h1>Top tents</h1><p>As an Amazon Associate I earn from qualifying purchases.</p><a href="https://www.amazon.com/dp/B012345678?tag=wrong-20">Tent</a>'
    result = audit_html(html, 'https://example.com/', 'right-20')
    assert result['summary']['amazon_links'] == 1
    assert any(i['rule'] == 'Amazon tag' for i in result['issues'])


def test_draft_relative_without_site():
    result = audit_html('<a href="/other-article/">Related guide</a>')
    assert result['links'][0]['link_type'] == 'Relative (base URL needed)'
