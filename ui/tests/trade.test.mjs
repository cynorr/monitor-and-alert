import test from 'node:test';
import assert from 'node:assert/strict';
import { quantityStep, quantityTicks, suggestedBuy, tradeRequest, TradeError, orderFieldsComplete, TradeController } from '../public/trade.js';
import { horizontalLines } from '../public/price-lines.js';
import { orderedTradeRows } from '../public/schwab-holdings.js';
import { openPercent, editableStop } from '../public/schwab-data.js';
import { loadTradeConfig } from '../public/trade-config.js';

test('automatic buy combines the day High and Schwab Ask; share steps follow the dollar scale', () => {
    assert.equal(suggestedBuy(101, 100), '101.00');
    assert.equal(suggestedBuy(100, 101), '101.01');
    assert.equal(suggestedBuy(null, 100), '');
    for (const [price, step] of [[10, 50], [50, 10], [100, 5], [250, 2], [500, 1], [1000, 1]]) assert.equal(quantityStep(price), step);
});
test('native P/L percentage does not use the chart price; sold rows stay at the tail', () => {
    assert.equal(openPercent({quantity:'10', average_price:'20', open_profit_loss:'10'}), 5);
    assert.equal(openPercent({quantity:'10', average_price:null, open_profit_loss:'10'}), null);
    const rows = [{ticker:'ZZZ',symbol:'ZZZ.US',kind:'sold'}, {ticker:'AAA',symbol:'AAA.US',kind:'holding'}, {ticker:'BBB',symbol:'BBB.US',kind:'entry'}];
    assert.deepEqual(orderedTradeRows(rows, 'symbol', {enabled:false,symbols:{}}).map(r => r.kind), ['entry','holding','sold']);
    assert.equal(editableStop({order_id:'1',editable:true,instruction:'SELL',order_type:'STOP',strategy_type:'SINGLE',child_orders:[],status:'AWAITING_PARENT_ORDER'}), false);
    for (const editable of [true,false]) assert.equal(editableStop({order_id:'1',editable,instruction:'SELL',order_type:'STOP',strategy_type:'SINGLE',child_orders:[],status:'PENDING_ACTIVATION'}),true);
});
test('quantity ticks label both endpoints, preserve exact Sell quantities and avoid crowded labels', () => {
    const ticks = quantityTicks(23, 5, 270);
    assert.deepEqual(ticks.map(tick => tick.quantity), [0,5,10,15,20,23]);
    assert.equal(ticks.at(-1).position, 100);
    for (const [maximum, step, width] of [[4500,50,270], [450,5,306], [45,1,270]]) {
        const labels = quantityTicks(maximum,step,width).filter(tick=>tick.label);
        assert.equal(labels[0].quantity,0); assert.equal(labels.at(-1).quantity,maximum);
        for (let i=1;i<labels.length;i++) assert.ok((labels[i].position-labels[i-1].position)/100*width >= 28);
    }
});
test('a disconnected write is unknown and is never automatically resent', async () => {
    globalThis.window = globalThis;
    let calls = 0;
    globalThis.fetch = async () => { calls++; throw new TypeError('disconnected'); };
    await assert.rejects(tradeRequest('orders/market-buy', 'POST', {symbol:'XYZ',qty:1}), error => error instanceof TradeError && error.unknown && error.message === 'Connection lost · result unknown');
    assert.equal(calls, 1);
});
test('known offline writes report Not sent and do not attempt the request', async () => {
    globalThis.window=globalThis;
    const navigator = Object.getOwnPropertyDescriptor(globalThis,'navigator');
    Object.defineProperty(globalThis,'navigator',{value:{onLine:false},configurable:true});
    let calls=0; globalThis.fetch=async()=>{calls++;};
    try {
        await assert.rejects(tradeRequest('orders/market-buy','POST',{symbol:'XYZ',qty:1}), error=>!error.unknown && error.message==='Not sent · offline');
        assert.equal(calls,0);
    } finally { if (navigator) Object.defineProperty(globalThis,'navigator',navigator); else delete globalThis.navigator; }
});

test('unstructured write failures and malformed success stay unknown; explicit preflight rejection does not', async () => {
    globalThis.window = globalThis;
    for (const response of [
        {ok:false,status:504,json:async()=>{throw new Error('html');}},
        {ok:true,status:201,json:async()=>({})},
    ]) {
        globalThis.fetch = async () => response;
        await assert.rejects(tradeRequest('orders/market-buy','POST',{symbol:'XYZ',qty:1}), error => error.unknown);
    }
    globalThis.fetch = async () => ({ok:false,status:503,json:async()=>({result:'error',error:{code:'SCHWAB_UNAVAILABLE'}})});
    await assert.rejects(tradeRequest('orders/market-buy','POST',{symbol:'XYZ',qty:1}), error => !error.unknown);
});

const settle = () => new Promise(resolve => setImmediate(resolve));
async function ticket() {
    const nodes = new Map(), modes = ['breakout-buy', 'market-buy', 'market-sell'];
    const node = id => {
        if (!nodes.has(id)) { const classes = new Set(); nodes.set(id, {
            value: '', textContent: '', hidden: false, disabled: false, clientWidth: 270, active: false, style: {}, dataset: {}, attributes: {}, listeners: {},
            classList: { toggle(name,on) { on ? classes.add(name) : classes.delete(name); }, contains:name=>classes.has(name) }, closest: () => null,
            setAttribute(key, value) { this.attributes[key] = value; },
            replaceChildren(...children) { this.children=children; },
            addEventListener(key, handler) { (this.listeners[key] ??= []).push(handler); },
            matches(selector) { return selector === ':active' && this.active; },
            setPointerCapture() {}, releasePointerCapture() {},
        }); }
        return nodes.get(id);
    };
    const buttons = modes.map(mode => Object.assign(node(mode), {dataset:{tradeMode:mode}}));
    globalThis.document = { getElementById: node, createElement:()=>node(Symbol()), querySelectorAll: () => buttons, addEventListener() {} };
    globalThis.ResizeObserver = class { observe() {} };
    globalThis.window = globalThis;
    const writes = [];
    globalThis.fetch = async (path, options) => {
        if (options.method !== 'GET') writes.push({path, method:options.method, body:JSON.parse(options.body)});
        return {ok:true,json:async()=>options.method === 'GET' ? {ask:'100',bid:'99',updated_at:'2026-10-27T14:00:00Z'} : {result:'accepted',new_order_id:'replacement'}};
    };
    const panels = ['daily','intraday'].map(id => {
        const axes = [], primitives = [], bounds = {top:0,left:0};
        return { id, axes, primitives, chart:{panes:()=>[{getHTMLElement:()=>({getBoundingClientRect:()=>bounds})}],paneSize:()=>({width:400,height:400})},
            candles:{attachPrimitive(primitive) { primitives.push(primitive); primitive.attached({requestUpdate(){}}); },
                priceToCoordinate:price=>300-price*2, coordinateToPrice:y=>(300-y)/2,
                createPriceLine(options) { const axis={options,applyOptions(next){Object.assign(this.options,next);}};axes.push(axis);return axis; },
                removePriceLine(axis) { axes.splice(axes.indexOf(axis),1); }},
        };
    });
    const stop = {symbol:'XYZ',order_id:'stop-1',stop_price:'80',quantity:'23',editable:true,instruction:'SELL',order_type:'STOP',strategy_type:'SINGLE',child_orders:[],status:'WORKING'};
    const state = {rows:[{symbol:'XYZ.US',ticker:'XYZ',position:{quantity:'23'},orders:[stop]}],orders:[stop],health:{auth_status:'valid',schwab_rest:'connected',schwab_stream:'connected'},limits:{buy_amount:'45000',loss:'2000',stop_ratio:'.15'}};
    const controller = new TradeController(panels, ()=>'trade', {spread_warning_percent:.5});
    controller.update(state); controller.setSymbol('XYZ.US'); await settle();
    const timestamp=Date.parse('2026-10-27T14:00:00Z')/1000;
    controller.view({symbol:'XYZ.US',server_time:timestamp,quote:{regular:{timestamp,high:102,low:95}}});
    const drag = (panel, price, dy) => {
        const host = node(panel.id+'-chart');
        for (const [type,y] of [['pointerdown',300-price*2],['pointermove',300-price*2+dy],['pointerup',300-price*2+dy]]) {
            const event={button:0,clientX:100,clientY:y,pointerId:1,target:host,preventDefault(){},stopImmediatePropagation(){}};
            for (const handler of host.listeners[type]) handler(event);
        }
    };
    return {node, panels, drag, writes, controller, state};
}
test('browse is draft-free; both charts edit the same prices and either drag unlocks Auto', async () => {
    const {node,panels,drag}=await ticket();
    assert.equal(node('trade-size').attributes['aria-hidden'],'true');
    for (const panel of panels) assert.deepEqual(panel.tradePrices,[80]);
    node('breakout-buy').onclick();
    assert.equal(node('trade-size').attributes['aria-hidden'],'false');
    assert.equal(node('trade-auto').disabled,true);
    drag(panels[0],102,-8);
    for (const panel of panels) assert.deepEqual(panel.tradePrices,[80,106,95]);
    assert.equal(node('trade-auto').disabled,false);
    node('trade-auto').onclick();
    drag(panels[1],95,6);
    for (const panel of panels) assert.deepEqual(panel.tradePrices,[80,102,92]);
    assert.equal(node('trade-auto').disabled,false);
    node('trade-auto').onclick();
    for (const panel of panels) assert.deepEqual(panel.tradePrices,[80,102,95]);
    node('breakout-buy').onclick();
    for (const panel of panels) assert.deepEqual(panel.tradePrices,[80]);
});
test('market references never become order prices; the Sell ruler can select all remaining shares', async () => {
    const {node,panels,writes}=await ticket();
    node('market-buy').onclick();
    assert.deepEqual(panels[0].tradePrices,[80,102,95]);
    node('trade-submit').onclick(); await settle();
    assert.deepEqual(writes,[{path:'/v1/trade/orders/market-buy',method:'POST',body:{symbol:'XYZ',qty:200}}]);
    assert.equal(node('trade-size').attributes['aria-hidden'],'true');
    node('market-sell').onclick();
    node('trade-ruler').value=node('trade-ruler').max; node('trade-ruler').oninput();
    assert.equal(node('trade-qty').textContent,'23');
    node('trade-submit').onclick(); await settle();
    assert.deepEqual(writes[1],{path:'/v1/trade/orders/market-sell',method:'POST',body:{symbol:'XYZ',qty:23}});
});
test('dragging an existing stop switches Send to one explicit replacement without a new order', async () => {
    const {node,panels,drag,writes}=await ticket();
    node('breakout-buy').onclick(); drag(panels[0],80,-10);
    assert.equal(writes.length,0);
    assert.equal(node('trade-ticket').dataset.editing,'stop');
    assert.equal(node('trade-submit').attributes['aria-label'],'Send stop change');
    assert.equal(node('trade-submit').disabled,false);
    for (const panel of panels) assert.deepEqual(panel.tradePrices,[85]);
    node('trade-submit').onclick(); await settle();
    assert.deepEqual(writes,[{path:'/v1/trade/orders/stop-1/stop',method:'PUT',body:{new_stop:'85.00'}}]);
    assert.equal(node('trade-submit').disabled,true);
});
test('pending-activation Stops edit outside Regular even with editable=false and accept the next snapshot', async () => {
    const {node,panels,drag,writes,controller,state}=await ticket();
    const stop={...state.orders[0],status:'PENDING_ACTIVATION',editable:false};
    const outside={...state,orders:[stop],rows:[{...state.rows[0],orders:[stop]}]};
    controller.update(outside);
    controller.view({symbol:'XYZ.US',server_time:Date.parse('2026-10-28T22:00:00Z')/1000,quote:{regular:null}});
    drag(panels[0],80,-10);
    assert.equal(node('trade-submit').disabled,false);
    assert.deepEqual(panels[1].tradePrices,[85]);
    node('trade-submit').onclick(); await settle();
    assert.deepEqual(writes[0],{path:'/v1/trade/orders/stop-1/stop',method:'PUT',body:{new_stop:'85.00'}});
    const replacement={...stop,order_id:'replacement',stop_price:'85'};
    controller.update({...outside,orders:[replacement],rows:[{...outside.rows[0],orders:[replacement]}]});
    drag(panels[1],85,-10);
    assert.equal(node('trade-submit').disabled,false);
    node('trade-submit').onclick(); await settle();
    assert.equal(writes[1].path,'/v1/trade/orders/replacement/stop');
});
test('native range input updates quantity and freezes its scale while dragging through quotes', async () => {
    const {node,controller}=await ticket(); node('market-buy').onclick();
    const ruler=node('trade-ruler'),maximum=ruler.max;
    ruler.active=true; ruler.value='17'; ruler.oninput();
    assert.equal(node('trade-qty').textContent,'85');
    controller.updateQuote({ask:'250',bid:'249',updated_at:'2026-10-27T14:00:01Z'});
    assert.equal(ruler.max,maximum);
    assert.equal(node('trade-qty').textContent,'85');
    ruler.value='20'; ruler.oninput();
    assert.equal(node('trade-qty').textContent,'100');
    assert.equal(node('trade-estimate').textContent,'25,000');
    ruler.active=false;
    controller.updateQuote({ask:'250',bid:'249',updated_at:'2026-10-27T14:00:02Z'});
    assert.equal(node('trade-qty').textContent,'100');
    assert.equal(ruler.value,'50');
});
test('Send uses the visible breakout draft once, including manual prices the backend may reject', async () => {
    const {node,panels,drag,writes}=await ticket();
    node('breakout-buy').onclick(); drag(panels[1],102,44);
    assert.equal(node('trade-submit').disabled,false);
    node('trade-submit').onclick(); await settle();
    assert.deepEqual(writes,[{path:'/v1/trade/orders/breakout-buy',method:'POST',body:{symbol:'XYZ',qty:196,buy_stop:'80.00',sell_stop:'95.00'}}]);
});
test('Accepted disappears after two seconds independently of snapshots; later errors remain', async t => {
    const {node,controller,state}=await ticket();
    t.mock.timers.enable({apis:['setTimeout']});
    node('market-buy').onclick(); node('trade-submit').onclick(); await settle();
    assert.equal(node('trade-message').textContent,'Accepted');
    t.mock.timers.tick(1000); controller.update(state);
    assert.equal(node('trade-message').textContent,'Accepted');
    t.mock.timers.tick(1000);
    assert.equal(node('trade-feedback').hidden,true);
    node('market-buy').onclick(); node('trade-submit').onclick(); await settle();
    globalThis.fetch=async()=>{throw new TypeError('disconnected');};
    node('market-buy').onclick(); node('trade-submit').onclick(); await settle();
    t.mock.timers.tick(2000);
    assert.equal(node('trade-message').textContent,'Connection lost · result unknown');
    assert.equal(node('trade-checked').hidden,false);
});
test('risk amount is an integer while its percentage retains precision', async () => {
    const {node}=await ticket();
    node('breakout-buy').onclick();
    node('trade-ruler').value='1'; node('trade-ruler').oninput();
    assert.equal(node('trade-risk').textContent,'Risk 6.86% ｜ 35');
});
test('filled order fields enable Send while the backend keeps financial validation', () => {
    assert.equal(orderFieldsComplete('breakout-buy','1','10','20'),true);
    assert.equal(orderFieldsComplete('breakout-buy','10000','100','1'),true);
    for (const values of [[null,'1','10','9'],['breakout-buy','1','','9'],['market-buy','0','',''],['market-sell','1.5','','']]) assert.equal(orderFieldsComplete(...values),false);
});
test('solid lines use one physical pixel on Retina and Alert keeps its dashed CSS width', () => {
    const ctx={setLineDash(value){this.dash=value;},beginPath(){},moveTo(){},lineTo(){},stroke(){this.width=this.lineWidth;}};
    const target={useBitmapCoordinateSpace:fn=>fn({context:ctx,bitmapSize:{width:800,height:800},horizontalPixelRatio:2,verticalPixelRatio:2})};
    horizontalLines(()=>[{y:10,color:'blue'}]).draw(target); assert.equal(ctx.width,1);
    horizontalLines(()=>[{y:10,color:'black'}],true).draw(target); assert.equal(ctx.width,2);
});

test('spread warning uses a configurable strict threshold and browse content stays empty', async () => {
    const {node,controller}=await ticket();
    assert.equal(node('trade-qty').textContent,'');
    assert.equal(node('trade-estimate').textContent,'');
    controller.updateQuote({ask:'100.5',bid:'100',updated_at:'2026-10-27T14:00:01Z'});
    assert.equal(node('trade-spread-percent').textContent,'0.50%');
    assert.equal(node('trade-spread-value').textContent,'0.50');
    assert.equal(node('trade-spread-percent').classList.contains('spread-wide'),false);
    controller.updateQuote({ask:'100.51',bid:'100',updated_at:'2026-10-27T14:00:02Z'});
    assert.equal(node('trade-spread-percent').classList.contains('spread-wide'),true);
});
test('UI config accepts a numeric percentage and reports invalid configuration', async () => {
    globalThis.fetch=async()=>({ok:true,json:async()=>({spread_warning_percent:.75})});
    assert.deepEqual(await loadTradeConfig(),{spread_warning_percent:.75});
    globalThis.fetch=async()=>({ok:true,json:async()=>({spread_warning_percent:'0.5'})});
    await assert.rejects(loadTradeConfig(),/Invalid Trade/);
});
