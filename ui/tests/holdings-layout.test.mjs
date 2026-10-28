import test from 'node:test';
import assert from 'node:assert/strict';
import { HoldingsLayout } from '../public/holdings-layout.js';

test('allocated table width and decorative overflow cannot raise the content minimum on refresh', () => {
    globalThis.ResizeObserver=class {observe(){}};
    globalThis.document={body:{append(){}}};
    globalThis.getComputedStyle=node=>node.style;
    const first={textContent:'XYZ',style:{display:'table-cell',borderLeftWidth:'1px'},getBoundingClientRect:()=>({left:10})};
    let allocated=680, intrinsic=450, copies=0;
    const scroll={style:{paddingLeft:'8px',paddingRight:'8px'},offsetWidth:680,clientWidth:680};
    const properties={};
    const table={className:'holdings-table',rows:[{cells:[first]}],tHead:{rows:[{cells:[{getBoundingClientRect:()=>({right:10+allocated})}]}]},tBodies:[{rows:[{cells:[first]}]}],
        getClientRects:()=>[{}],closest:()=>scroll,style:{setProperty(key,value){properties[key]=value;}},
        get scrollWidth(){throw new Error('Allocated scrollWidth must not be measured');},
        cloneNode(){copies++;return {removeAttribute(){},querySelectorAll:()=>[],classList:{add(){}},setAttribute(){},remove(){},getBoundingClientRect:()=>({width:intrinsic})};},
    };
    const widths=[],layout=new HoldingsLayout(table,()=>0,width=>widths.push(width));
    layout.measure();
    for (let i=0;i<80;i++){allocated+=1;layout.measure();}
    assert.equal(copies,1);
    assert.ok(widths.every(width=>width===466));
    assert.equal(properties['--holding-price-width'],`${allocated-1}px`);
    intrinsic=500;first.textContent='LONGER';layout.measure();assert.equal(widths.at(-1),516);
});
