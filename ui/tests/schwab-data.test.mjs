import test from 'node:test';
import assert from 'node:assert/strict';
import { activeOrders, entryAmount, holdingTags, holdingDetails } from '../public/schwab-data.js';

const order = (id, changes={}) => ({order_id:id,parent_order_id:null,symbol:'XYZ',instruction:'SELL',order_type:'STOP',strategy_type:'SINGLE',status:'WORKING',quantity:'100',filled_quantity:'0',stop_price:'48',cancelable:true,editable:true,child_orders:[],executions:[],...changes});
const position = {symbol:'XYZ',quantity:'80',average_price:'50',market_value:'4400',open_profit_loss:'400'};
const row = changes => ({symbol:'XYZ.US',ticker:'XYZ',kind:'holding',position,orders:[],sold_today:null,...changes});
test('Entry keeps each native parent-child pair and cancels only its parent', () => {
    const child=order('child',{parent_order_id:'parent',status:'AWAITING_PARENT_ORDER'});
    const parent=order('parent',{instruction:'BUY',stop_price:'50',strategy_type:'TRIGGER',child_orders:[child]});
    const data=row({kind:'entry',position:null,orders:[parent,child]});
    assert.equal(activeOrders(data).length,2);
    assert.equal(entryAmount(data),5000);
    assert.deepEqual(holdingDetails(data),[{key:'entry-parent',kind:'Entry',qty:100,price:50,stop:48,amount:5000,pnlPercent:null,pnl:null,riskPercent:4,risk:200,cancelId:'parent'}]);
    assert.deepEqual(holdingTags(data),['Entry']);
    const second=order('second',{instruction:'BUY',stop_price:'60',child_orders:[order('second-child',{stop_price:'57'})]});
    const pair=row({position:null,orders:[parent,child,second]});
    assert.equal(entryAmount(pair),11000);
    assert.deepEqual(holdingDetails(pair).map(value=>[value.stop,value.risk]),[[48,200],[57,300]]);
});
test('Buy is only the current native average-cost summary; missing cost silently skips it', () => {
    const data=row({orders:[order('old-buy',{instruction:'BUY',status:'FILLED',quantity:'200',stop_price:'20'})]});
    assert.deepEqual(holdingDetails(data),[{key:'buy',kind:'Buy',qty:80,price:50,stop:null,amount:4000,pnlPercent:null,pnl:null,riskPercent:null,risk:null,cancelId:null}]);
    assert.deepEqual(holdingDetails(row({position:{...position,average_price:null}})),[]);
});
test('Sold groups fills by real order while multiple Stops keep their own quantities and actions', () => {
    const sold={quantity:'30',amount:'1660',average_price:'55.33',executions:[
        {order_id:'sale-1',quantity:'10',price:'55'}, {order_id:'sale-1',quantity:'10',price:'56'}, {order_id:'sale-2',quantity:'10',price:'55'},
    ]};
    const data=row({sold_today:sold,orders:[order('s1',{quantity:'30'}),order('s2',{quantity:'50',cancelable:false})]});
    const details=holdingDetails(data);
    assert.deepEqual(details.map(value=>value.kind),['Buy','Sold','Sold','Stop','Stop']);
    assert.deepEqual(details.filter(value=>value.kind==='Sold').map(value=>[value.qty,value.price,value.amount]),[[20,55.5,1110],[10,55,550]]);
    assert.deepEqual(details.filter(value=>value.kind==='Sold').map(value=>[value.pnlPercent,value.pnl]),[[11,110],[10,50]]);
    assert.deepEqual(details.filter(value=>value.kind==='Stop').map(value=>[value.qty,value.cancelId]),[[30,'s1'],[50,null]]);
    assert.deepEqual(details.filter(value=>value.kind==='Stop').map(value=>[value.pnlPercent,value.pnl]),[[-4,-60],[-4,-100]]);
    assert.deepEqual(holdingTags(data),['Trim']);
    assert.deepEqual(holdingTags({...data,position:null,orders:[],kind:'sold'}),[]);
    assert.deepEqual(holdingTags({...data,orders:[order('buy',{instruction:'BUY'})]}),['Entry','Trim']);
});
test('market Entry keeps its native missing price and risk empty', () => {
    const data=row({position:null,orders:[order('market',{instruction:'BUY',order_type:'MARKET',stop_price:null})]});
    assert.equal(entryAmount(data),null);
    const [detail]=holdingDetails(data);
    assert.equal(detail.amount,null); assert.equal(detail.risk,null); assert.equal(detail.cancelId,'market');
});
test('Buy P/L stays empty while every Stop uses its own quantity and stop price', () => {
    const details=holdingDetails(row({position:{...position,market_value:'9999'},orders:[order('loss',{quantity:'30'}),order('gain',{quantity:'50',stop_price:'53'})]}));
    assert.deepEqual(details.map(value=>[value.pnlPercent,value.pnl]),[[null,null],[-4,-60],[6,150]]);
    const [buy]=holdingDetails(row({position:{...position,open_profit_loss:null}}));
    assert.equal(buy.pnl,null); assert.equal(buy.pnlPercent,null);
});
test('Sold estimates use the current broker average and leave fully closed or missing-cost rows empty', () => {
    const sale={executions:[{order_id:'sale',quantity:'20',price:'55'}]};
    const data=row({position:{...position,average_price:'52'},sold_today:sale,orders:[order('old-buy',{instruction:'BUY',status:'FILLED',executions:[{quantity:'100',price:'20'}]})]});
    const sold=holdingDetails(data).find(value=>value.kind==='Sold');
    assert.equal(sold.pnl,60); assert.ok(Math.abs(sold.pnlPercent-3/52*100)<1e-10);
    for (const missing of [null,{...position,average_price:null},{...position,average_price:'0'}]) {
        const rows=holdingDetails(row({position:missing,sold_today:sale,orders:[order('stop')]}));
        for (const detail of rows.filter(value=>value.kind==='Sold'||value.kind==='Stop')) {assert.equal(detail.pnl,null);assert.equal(detail.pnlPercent,null);}
    }
});
