from qa_engine import amazon_details, allowed_url

def test_amazon_product():
    assert amazon_details('https://www.amazon.com/dp/B0ABCDEFGH?tag=sample-20') == ('B0ABCDEFGH', 'sample-20')

def test_non_amazon():
    assert amazon_details('https://example.com/dp/B012345678?tag=test') == ('', '')

def test_block_private_urls():
    assert not allowed_url('http://127.0.0.1/admin')
    assert not allowed_url('http://169.254.169.254/latest/meta-data/')
    assert not allowed_url('file:///etc/passwd')
