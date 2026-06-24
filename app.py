#!/usr/bin/env python3
"""
Call Option Analyzer - serves both the frontend HTML and backend API.
"""
import os
try:
    import yfinance as yf
    from flask import Flask, jsonify, send_from_directory, request
    from flask_cors import CORS
except ImportError:
    print("\n  Missing dependencies. Run:\n  pip install yfinance flask flask-cors\n")
    raise

app = Flask(__name__, static_folder='static')
CORS(app)

def safe_float(val, default=0.0):
    try:
        v = float(val)
        return default if (v != v) else v
    except (TypeError, ValueError):
        return default

def safe_int(val, default=0):
    try:
        v = float(val)
        return default if (v != v) else int(v)
    except (TypeError, ValueError):
        return default

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/quote/<ticker>')
def quote(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info
        price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose')
        prev  = info.get('regularMarketPreviousClose') or info.get('previousClose') or price
        if not price:
            return jsonify({'error': 'No price data found for ' + ticker}), 404
        return jsonify({
            'price':  safe_float(price),
            'prev':   safe_float(prev),
            'name':   info.get('longName') or info.get('shortName') or ticker.upper(),
            'sector': info.get('sector', ''),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chain/<ticker>')
def chain(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        dates = list(t.options)
        if not dates:
            return jsonify({'error': 'No options found for ' + ticker}), 404
        return jsonify({'expirations': dates})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chain/<ticker>/<expiry>')
def chain_date(ticker, expiry):
    try:
        t = yf.Ticker(ticker.upper())
        opt = t.option_chain(expiry)
        calls = opt.calls
        rows = []
        for _, r in calls.iterrows():
            rows.append({
                'strike':            safe_float(r.get('strike')),
                'lastPrice':         safe_float(r.get('lastPrice')),
                'bid':               safe_float(r.get('bid')),
                'ask':               safe_float(r.get('ask')),
                'volume':            safe_int(r.get('volume')),
                'openInterest':      safe_int(r.get('openInterest')),
                'impliedVolatility': safe_float(r.get('impliedVolatility')),
                'inTheMoney':        bool(r.get('inTheMoney', False)),
            })
        return jsonify({'calls': rows})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/history/<ticker>')
def history(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        # Try multiple approaches in case one fails
        hist = None
        for period in ['3mo', '90d']:
            try:
                hist = t.history(period=period)
                if not hist.empty:
                    break
            except Exception:
                continue
        # Fallback: use download
        if hist is None or hist.empty:
            import datetime
            end = datetime.date.today()
            start = end - datetime.timedelta(days=92)
            hist = yf.download(ticker.upper(), start=str(start), end=str(end), progress=False)
        if hist is None or hist.empty:
            return jsonify({'error': 'No history found for ' + ticker}), 404
        # Flatten MultiIndex columns if present (yf.download returns them)
        if hasattr(hist.columns, 'levels'):
            hist.columns = hist.columns.get_level_values(0)
        dates  = [str(d.date()) if hasattr(d, 'date') else str(d)[:10] for d in hist.index]
        closes = [round(float(v), 4) for v in hist['Close']]
        return jsonify({'dates': dates, 'closes': closes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/peers/<ticker>')
def peers(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info
        sector   = info.get('sector', '')
        industry = info.get('industry', '')
        name     = info.get('longName') or info.get('shortName') or ticker.upper()

        if not sector and not industry:
            return jsonify({'error': 'No sector data for ' + ticker, 'peers': []}), 200

        # Use yfinance recommendations/similar — most reliable cross-version method
        peer_list = []

        # Method 1: recommendations (works in most yfinance versions)
        try:
            recs = t.recommendations
            if recs is not None and not recs.empty:
                syms = recs['symbol'].dropna().unique().tolist() if 'symbol' in recs.columns else []
                for sym in syms[:20]:
                    if sym == ticker.upper():
                        continue
                    try:
                        pt = yf.Ticker(sym)
                        pi = pt.fast_info
                        peer_list.append({
                            'ticker':    sym,
                            'name':      sym,
                            'price':     safe_float(getattr(pi, 'last_price', 0)),
                            'prev':      safe_float(getattr(pi, 'previous_close', 0)),
                            'change':    safe_float(getattr(pi, 'last_price', 0)) - safe_float(getattr(pi, 'previous_close', 0)),
                            'changePct': 0,
                            'marketCap': safe_float(getattr(pi, 'market_cap', 0)),
                        })
                    except Exception:
                        continue
        except Exception:
            pass

        # Method 2: fallback — use Yahoo Finance quote summary similarSecurities
        if not peer_list:
            try:
                import requests as req
                url = f'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker.upper()}?modules=recommendationTrend,financialData'
                headers = {'User-Agent': 'Mozilla/5.0'}
                r = req.get(url, headers=headers, timeout=8)
                data = r.json()
                result = (data.get('quoteSummary') or {}).get('result') or []
                if result:
                    # Try to get peers from a different endpoint
                    url2 = f'https://query1.finance.yahoo.com/v6/finance/recommendationsbysymbol/{ticker.upper()}'
                    r2 = req.get(url2, headers=headers, timeout=8)
                    d2 = r2.json()
                    finance = (d2.get('finance') or {})
                    results = finance.get('result') or []
                    for item in results:
                        for rec in (item.get('recommendedSymbols') or []):
                            sym = rec.get('symbol', '')
                            if not sym or sym == ticker.upper():
                                continue
                            peer_list.append({
                                'ticker': sym, 'name': sym,
                                'price': 0, 'prev': 0, 'change': 0, 'changePct': 0, 'marketCap': 0,
                            })
            except Exception:
                pass

        # Enrich peer_list with quotes if prices are missing
        enriched = []
        for p in peer_list[:20]:
            if p['price'] == 0:
                try:
                    pi = yf.Ticker(p['ticker']).fast_info
                    price = safe_float(getattr(pi, 'last_price', 0))
                    prev  = safe_float(getattr(pi, 'previous_close', 0))
                    p['price']     = price
                    p['prev']      = prev
                    p['change']    = price - prev
                    p['changePct'] = ((price - prev) / prev * 100) if prev else 0
                    p['marketCap'] = safe_float(getattr(pi, 'market_cap', 0))
                except Exception:
                    pass
            enriched.append(p)

        enriched.sort(key=lambda x: x['marketCap'], reverse=True)

        return jsonify({
            'ticker':   ticker.upper(),
            'name':     name,
            'sector':   sector,
            'industry': industry,
            'peers':    enriched[:20]
        })
    except Exception as e:
        return jsonify({'error': str(e), 'peers': []}), 500

@app.route('/quotes/batch')
def quotes_batch():
    tickers = request.args.get('tickers', '')
    if not tickers:
        return jsonify({'quotes': []})
    symbols = [t.strip().upper() for t in tickers.split(',') if t.strip()][:25]
    results = []
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            fi = t.fast_info
            price = safe_float(getattr(fi, 'last_price', 0))
            prev  = safe_float(getattr(fi, 'previous_close', 0))
            name  = sym
            try:
                info = t.info
                name = info.get('longName') or info.get('shortName') or sym
            except Exception:
                pass
            results.append({
                'ticker': sym,
                'price':  price,
                'prev':   prev,
                'name':   name,
            })
        except Exception as e:
            results.append({'ticker': sym, 'error': str(e)})
    return jsonify({'quotes': results})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f'\n  Starting on port {port}...\n')
    app.run(host='0.0.0.0', port=port)
