import { useEffect, useRef, useState } from "react";
import { Paperclip, Globe, Mic, Plus } from "lucide-react";
import { toast } from "sonner"
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { apiQuery, sendMessageToClient, type DataResponse } from "./service";

interface Message {
	id: string;
	role: "user" | "assistant";
	content: string | DataResponse;
}

export function AgentInterface() {
	const [messages, setMessages] = useState<Message[]>([]);
	const [input, setInput] = useState("");
	const [selectedOption, setSelectedOption] = useState<string>("api");
	const [isLoading, setIsLoading] = useState(false);
	// const [error, setError] = useState<string | null>(null);

	const options = [
		{ id: "a2a", label: "A2A", icon: Paperclip },
		{ id: "mcp", label: "MCP Server", icon: Globe },
		{ id: "api", label: "API", icon: Mic }
	];

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!input.trim()) return;
		const userMessage: Message = {
			id: crypto.randomUUID(),
			role: "user",
			content: input,
		};
		const _tempAssistantMessage: Message = {
			id: crypto.randomUUID(),
			role: "assistant",
			content: "",
		};
		setMessages((prev) => [...prev, userMessage, _tempAssistantMessage]);
		setInput("");

		setIsLoading(true);
		// setError(null);

		try {
			if (selectedOption === "a2a") {
				const response = await sendMessageToClient(input, "a2a");
				const assistantMessage: Message = {
					id: crypto.randomUUID(),
					role: "assistant",
					content: response,
				};
				setMessages((prev) => [...prev, assistantMessage]);
			} else if (selectedOption === "mcp") {
				const response = await sendMessageToClient(input, "mcp");
				const assistantMessage: Message = {
					id: crypto.randomUUID(),
					role: "assistant",
					content: response,
				};
				setMessages((prev) => [...prev, assistantMessage]);
			} else if (selectedOption === "api") {
				const response = await apiQuery(input);
				if ((response as any)?.status === 'error') {
					toast("Error", {
						description: (response as any).message.error,
					})
					setMessages((prev) => [...prev, {
						id: crypto.randomUUID(),
						role: "assistant",
						content: "Failed to execute the query!" as string
					}]);
					return;
				}
				const assistantMessage: Message = {
					id: crypto.randomUUID(),
					role: "assistant",
					content: response as DataResponse
				};
				setMessages((prev) => [...prev, assistantMessage]);
			}
		} catch (error) {
			// setError(error as string);
			setMessages((prev) => [...prev, {
				id: crypto.randomUUID(),
				role: "assistant",
				content: "Got error while executing the query!" as string
			}]);
			toast("Error", {
				description: error as string,
			})
		} finally {
			setIsLoading(false);
		}
	};

	const messagesEndRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [messages, isLoading]);

	return (
		<div className="flex flex-col h-screen bg-[#212121] text-white w-full">
			{/* Messages Area */}
			<div className="flex-1 overflow-y-auto">
				{messages.length === 0 ? (
					<div className="flex items-center justify-center h-full">
						<h1 className="text-3xl font-medium text-white/90">
							What can I help with?
						</h1>
					</div>
				) : (
					<div className="max-w-3xl mx-auto py-8 px-4 space-y-6">
						{messages.map((message, index) => (
							<div
								key={message.id}
								className={`flex ${message.role === "user" ? "justify-end" : "justify-start"
									}`}
							>
								<div
									className={`max-w-[80%] rounded-2xl px-4 py-3 ${message.role === "user"
										? "bg-[#2f2f2f] text-white"
										: "bg-transparent text-white/90"
										}`}
								>
									{typeof message.content === "string" ? (
										message.content
									) : (
										<div className="space-y-4 w-full">
											{/* Query Display */}
											<div className="bg-[#1a1a1a] rounded-lg p-3">
												<p className="text-sm text-white/60 mb-1">Query:</p>
												<code className="text-sm text-emerald-400 font-mono">
													{message.content.data?.query}
												</code>
											</div>

											{/* Summary */}
											{message.content.data?.one_line_summary && (
												<p className="text-sm text-white/80">
													{message.content.data?.one_line_summary}
												</p>
											)}

											{/* Results Table */}
											{message.content.data?.results && message.content.data?.results?.length > 0 && (
												<div className="overflow-x-auto rounded-lg border border-white/10">
													<Table>
														<TableHeader>
															<TableRow className="border-white/10 hover:bg-transparent">
																{Object.keys(message.content.data?.results?.[0] || {})
																	.filter((key) => (message.content as DataResponse)?.data?.results?.some((row) => row[key] !== null))
																	.map((key) => (
																		<TableHead key={key} className="text-white/70 font-medium text-xs">
																			{key}
																		</TableHead>
																	))}
															</TableRow>
														</TableHeader>
														<TableBody>
															{message.content.data?.results?.slice(0, 50).map((row, rowIndex) => (
																<TableRow key={rowIndex} className="border-white/10 hover:bg-white/5">
																	{Object.keys((message.content as DataResponse)?.data?.results?.[0] || {})
																		.filter((key) => (message.content as DataResponse)?.data?.results.some((r: Record<string, any>) => r[key] !== null))
																		.map((key) => (
																			<TableCell key={key} className="text-white/80 text-xs py-2">
																				{row[key] !== null ? String(row[key]) : "-"}
																			</TableCell>
																		))}
																</TableRow>
															))}
														</TableBody>
													</Table>
													{ message.content?.data?.results && message.content?.data?.results?.length > 50 && (
														<p className="text-xs text-white/50 p-2 text-center">
															Showing 50 of {message.content.data?.result_count} results
														</p>
													)}
												</div>
											)}

											{/* Result count */}
											<p className="text-xs text-white/50">
												{message.content.data?.result_count} results found
											</p>
										</div>
									)}
									{message.role === "assistant" && index === messages.length - 1 && isLoading && (
										<p className="text-gray-500 flex items-center gap-1">
											Loading
											<span className="animate-bounce">.</span>
											<span className="animate-bounce [animation-delay:0.2s]">.</span>
											<span className="animate-bounce [animation-delay:0.4s]">.</span>
										</p>
									)}
								</div>
							</div>
						))}
						<div ref={messagesEndRef} />
					</div>
				)}
			</div>

			{/* Input Area */}
			<div className="p-4 pb-8">
				<div className="max-w-3xl mx-auto">
					<form onSubmit={handleSubmit}>
						<div className="bg-[#2f2f2f] rounded-3xl p-3">
							<Input
								autoFocus
								value={input}
								onChange={(e) => setInput(e.target.value)}
								placeholder="Ask anything"
								className="bg-transparent border-none text-white placeholder:text-white/50 text-base focus-visible:ring-0 focus-visible:ring-offset-0 mb-2"
							/>
							<div className="flex items-center justify-between">
								<div className="flex items-center gap-1">
									{options.map((option) => {
										const Icon = option.icon;
										const isActive = selectedOption === option.id;

										return (
											<Button
												key={option.id}
												type="button"
												variant="ghost"
												size="sm"
												onClick={() => setSelectedOption(option.id)}
												className={`rounded-full px-3 py-1.5 h-auto text-sm gap-1.5 transition-colors ${isActive
													? "bg-[#424242] text-white hover:bg-[#4a4a4a]!"
													: "bg-transparent text-white/60 hover:bg-[#3a3a3a]! hover:text-white/80!"
													}`}
											>
												<Icon className="w-4 h-4" />
												{option.label}
											</Button>
										);
									})}
								</div>

								<Button
									type="submit"
									size="icon"
									disabled={!input.trim()}
									className="rounded-full bg-white! text-black! hover:bg-white/90 disabled:opacity-30 disabled:bg-white/20 h-8 w-8"
								>
									<Plus />
								</Button>
							</div>
						</div>
					</form>
				</div>
			</div>
		</div>
	);
}

export default AgentInterface;