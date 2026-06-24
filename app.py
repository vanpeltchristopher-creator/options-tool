#!/usr/bin/env python3
"""
Call Option Analyzer - serves both the frontend HTML and backend API.
"""
import os
try:
    import yfinance as yf
    from flask import Flask, jsonify, send_from_directory
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

        # Use yfinance screener to find peers in same industry
        screener = yf.Screener()
        screener.set_predefined_body('most_actives')
        body = {
            'offset': 0,
            'size': 100,
            'sortField': 'marketcap',
            'sortType': 'DESC',
            'quoteType': 'EQUITY',
            'query': {
                'operator': 'AND',
                'operands': [
                    {'operator': 'EQ', 'operands': ['sector', sector]},
                    {'operator': 'EQ', 'operands': ['industry', industry]},
                ]
            }
        }
        screener.set_body(body)
        resp = screener.response
        quotes = resp.get('quotes', [])

        peer_list = []
        for q in quotes:
            sym = q.get('symbol', '')
            if not sym or sym == ticker.upper():
                continue
            peer_list.append({
                'ticker':    sym,
                'name':      q.get('longName') or q.get('shortName') or sym,
                'price':     safe_float(q.get('regularMarketPrice')),
                'prev':      safe_float(q.get('regularMarketPreviousClose')),
                'change':    safe_float(q.get('regularMarketChange')),
                'changePct': safe_float(q.get('regularMarketChangePercent')),
                'marketCap': safe_float(q.get('marketCap')),
            })

        # Sort by market cap descending
        peer_list.sort(key=lambda x: x['marketCap'], reverse=True)

        return jsonify({
            'ticker':   ticker.upper(),
            'name':     name,
            'sector':   sector,
            'industry': industry,
            'peers':    peer_list[:25]
        })
    except Exception as e:
        return jsonify({'error': str(e), 'peers': []}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f'\n  Starting on port {port}...\n')
    app.run(host='0.0.0.0', port=port)
