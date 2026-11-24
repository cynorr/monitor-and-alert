import test from 'node:test';
import assert from 'node:assert/strict';
import { activeOrders, entryAmount, holdingTags, holdingDetails } from '../public/schwab-data.js';

const order = (id, changes={}) => ({order_id:id,parent_order_id:null,symbol:'XYZ',instruction:'SELL',order_type:'STOP',strategy_type:'SINGLE',status:'WORKING',quantity:'100',filled_quantity:'0',stop_price:'48',cancelable:true,editable:true,child_orders:[],executions:[],...changes});
const position = {symbol:'XYZ',quantity:'80',average_price:'50',market_value:'4400',open_profit_loss:'400'};
const row = changes => ({symbol:'XYZ.US',ticker:'XYZ',kind:'holding',position,orders:[],sold_today:null,trades:[],holding_days:10,days_over_year:false,sold_percent:null,is_new:false,...changes});
const trade = (id, side, changes={}) => ({order_id:id,side,time:'2026-11-18T15:00:00Z',date:'2026-11-18',quantity:'100',price:'50',amount:'5000',pnl:null,pnl_percent:null,holding_days:null,...changes});

test('Entry retains its native parent-child pairing and only the parent cancel action', () => {
    const child=order('child',{parent_order_id:'parent',status:'AWAITING_PARENT_ORDER'});
    const parent=order('parent',{instruction:'BUY',stop_price:'50',strategy_type:'TRIGGER',child_orders:[child]});
    const data=row({kind:'entry',position:null,orders:[parent,child]});
    assert.equal(activeOrders(data).length,2);
    assert.equal(entryAmount(data),5000);
    assert.deepEqual(holdingDetails(data),[{key:'entry-parent',kind:'Entry',date:null,days:null,qty:100,price:50,stop:48,amount:5000,pnlPercent:null,pnl:null,riskPercent:4,risk:200,cancelId:'parent'}]);
    assert.deepEqual(holdingTags(data),['Entry']);
});
test('historical Buy orders stay distinct and never display profit', () => {
    const data=row({trades:[trade('b1','BUY'),trade('b2','BUY',{quantity:'200',price:'60',amount:'12000'})]});
    const details=holdingDetails(data);
    assert.deepEqual(details.map(d=>[d.key,d.qty,d.price,d.amount]),[['trade-b1',100,50,5000],['trade-b2',200,60,12000]]);
    assert.ok(details.every(d=>d.pnl===null && d.pnlPercent===null && d.cancelId===null));
    assert.equal(details[0].date,'2026-11-18');
});
test('missing history skips Buy rows instead of fabricating an average-cost purchase', () => {
    assert.deepEqual(holdingDetails(row({})),[]);
});
test('Sold consumes backend FIFO profit and age independently of current broker average', () => {
    const sold=trade('s1','SELL',{quantity:'20',price:'55',amount:'1100',pnl:'200',pnl_percent:'22.2222',holding_days:10});
    for (const current of [position,{...position,average_price:'200'},null]) {
        const [detail]=holdingDetails(row({position:current,trades:[sold]}));
        assert.deepEqual([detail.qty,detail.pnl,detail.pnlPercent,detail.days],[20,200,22.2222,10]);
        assert.equal(detail.cancelId,null);
    }
});
test('NEW marks a real purchase today while Entry remains separate; prior sales add no tag', () => {
    assert.deepEqual(holdingTags(row({sold_today:{quantity:'30'}})),[]);
    assert.deepEqual(holdingTags(row({is_new:true})),['NEW']);
    assert.deepEqual(holdingTags(row({is_new:true,orders:[order('buy',{instruction:'BUY'})]})),['Entry','NEW']);
});
test('multiple active Stops retain individual quantities, average-cost estimates and cancel actions', () => {
    const details=holdingDetails(row({orders:[order('s1',{quantity:'30'}),order('s2',{quantity:'50',cancelable:false})]}));
    assert.deepEqual(details.map(d=>[d.kind,d.qty,d.amount,d.pnl,d.cancelId]),[['Stop',30,1440,-60,'s1'],['Stop',50,2400,-100,null]]);
    assert.ok(details.every(d=>d.date===null && d.days===null));
});
test('market Entry keeps missing native prices and risk blank', () => {
    const [detail]=holdingDetails(row({position:null,orders:[order('market',{instruction:'BUY',order_type:'MARKET',stop_price:null})]}));
    assert.equal(detail.amount,null); assert.equal(detail.risk,null); assert.equal(detail.cancelId,'market');
});
