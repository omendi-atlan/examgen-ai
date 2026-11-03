import { NextResponse } from "next/server";
export function GET(){return NextResponse.json({status:"ok",service:"examgen-ai",version:"0.2.0",aiConfigured:Boolean(process.env.OPENAI_API_KEY)});}
