app = workflow.compile()
 
@cl.on_message
async def on_message(msg: cl.Message):
    # Invoke the workflow with the user's message
    result = app.invoke({
        "messages": [
            {
                "role": "user",
                "content": msg.content
            }
        ]
    })
    # Extract and print the output from the result variable
    final_answer = cl.Message(content="")
    for m in result["messages"]:
        if isinstance(m, AIMessage):
            await final_answer.stream_token(f"🔨 {m.content}")
        elif isinstance(m, ToolMessage):
            await final_answer.stream_token(f"🤖 {m.content}")
 
        # Stream a blank line after each message
        await final_answer.stream_token("\n\n")
 
    await final_answer.send()