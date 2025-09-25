import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
	getRequestDetailApiRequestsRequestIdGetOptions,
	getRequestRawApiRequestsRequestIdRawGetOptions,
} from "@/client/@tanstack/react-query.gen";
import {
	Card,
	Descriptions,
	Tag,
	Table,
	Empty,
	Spin,
	Button,
	Typography,
	Space,
	Tabs,
	List,
	Modal,
	message,
} from "antd";
import { LinkOutlined, FlagOutlined, CodeOutlined } from "@ant-design/icons";
import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import type { ColumnsType } from "antd/es/table";

const { Text, Paragraph } = Typography;

export const Route = createFileRoute("/service/$port/request/$id")({
	component: RequestDetail,
});

function RequestDetail() {
	const { id, port } = Route.useParams();
	const requestId = parseInt(id);
	const navigate = useNavigate();
	const [rawModalVisible, setRawModalVisible] = useState(false);

	const { data, isLoading, error } = useQuery({
		...getRequestDetailApiRequestsRequestIdGetOptions({
			path: { request_id: requestId },
		}),
	});

	const {
		data: rawData,
		refetch: fetchRawData,
		isLoading: loadingRawData,
	} = useQuery({
		...getRequestRawApiRequestsRequestIdRawGetOptions({
			path: { request_id: requestId },
		}),
		enabled: false,
	});

	if (isLoading) {
		return (
			<div className="flex justify-center items-center h-64">
				<Spin size="large" tip="Loading request details..." />
			</div>
		);
	}

	if (error || !data) {
		return (
			<div className="flex justify-center items-center h-64">
				<Empty description={error?.message || "Request not found"} />
			</div>
		);
	}

	const { request, response } = data;

	const headerColumns: ColumnsType<any> = [
		{
			title: "Name",
			dataIndex: "name",
			key: "name",
			width: 200,
			render: (text: string) => <Text code>{text}</Text>,
		},
		{
			title: "Value",
			dataIndex: "value",
			key: "value",
			ellipsis: true,
			render: (text: string) => (
				<Text className="font-mono text-xs">{text}</Text>
			),
		},
	];

	const flagColumns: ColumnsType<any> = [
		{
			title: "Flag",
			dataIndex: "flag",
			key: "flag",
			render: (text: string) => (
				<Text code className="text-red-500">
					{text}
				</Text>
			),
		},
		{
			title: "Location",
			dataIndex: "location",
			key: "location",
			render: (text: string | null) =>
				text || <Text type="secondary">N/A</Text>,
		},
	];

	const linkedRequestColumns: ColumnsType<any> = [
		{
			title: "Direction",
			dataIndex: "direction",
			key: "direction",
			width: 100,
			render: (dir: string) => (
				<Tag color={dir === "incoming" ? "blue" : "green"}>
					{dir === "incoming" ? "← IN" : "OUT →"}
				</Tag>
			),
		},
		{
			title: "ID",
			dataIndex: "id",
			key: "id",
			width: 80,
		},
		{
			title: "Method",
			dataIndex: "method",
			key: "method",
			width: 80,
			render: (method: string) => (
				<Tag
					color={
						method === "GET"
							? "blue"
							: method === "POST"
								? "green"
								: method === "PUT"
									? "orange"
									: method === "DELETE"
										? "red"
										: "default"
					}
					className="text-xs"
				>
					{method}
				</Tag>
			),
		},
		{
			title: "Path",
			dataIndex: "path",
			key: "path",
			ellipsis: true,
			render: (path: string) => (
				<Text className="font-mono text-xs">{path}</Text>
			),
		},
		{
			title: "Time",
			dataIndex: "time",
			key: "time",
			width: 80,
			render: (time: string) => <Text className="text-xs">{time}</Text>,
		},
		{
			title: "Action",
			key: "action",
			width: 60,
			render: (_, record: any) => (
				<Button
					size="small"
					type="link"
					icon={<LinkOutlined />}
					onClick={() =>
						navigate({ to: `/service/${port}/request/${record.id}` })
					}
				>
					View
				</Button>
			),
		},
	];

	const requestTabItems = [
		{
			key: "info",
			label: "Info",
			children: (
				<Descriptions column={1} size="small">
					<Descriptions.Item label="Method">
						<Tag>{request.method}</Tag>
					</Descriptions.Item>
					<Descriptions.Item label="Path">
						<Text code>{request.path}</Text>
					</Descriptions.Item>
					<Descriptions.Item label="Time">
						{new Date(request.timestamp).toLocaleString()}
					</Descriptions.Item>
					<Descriptions.Item label="User Agent">
						<Text className="text-xs">{request.user_agent || "N/A"}</Text>
					</Descriptions.Item>
					<Descriptions.Item label="Blocked">
						{request.is_blocked ? (
							<Tag color="error">BLOCKED</Tag>
						) : (
							<Tag color="success">ALLOWED</Tag>
						)}
					</Descriptions.Item>
				</Descriptions>
			),
		},
		{
			key: "headers",
			label: `Headers (${request.headers.length})`,
			children:
				request.headers.length > 0 ? (
					<Table
						columns={headerColumns}
						dataSource={request.headers}
						rowKey="name"
						size="small"
						pagination={false}
					/>
				) : (
					<Empty description="No headers" />
				),
		},
		{
			key: "query",
			label: `Query Params (${Object.keys(request.query_params).length})`,
			children:
				Object.keys(request.query_params).length > 0 ? (
					<Descriptions column={1} size="small">
						{Object.entries(request.query_params).map(([key, value]) => (
							<Descriptions.Item key={key} label={key}>
								<Text code>{value}</Text>
							</Descriptions.Item>
						))}
					</Descriptions>
				) : (
					<Empty description="No query parameters" />
				),
		},
		{
			key: "body",
			label: "Body",
			children: request.body ? (
				<Paragraph>
					<pre className="bg-gray-100 p-2 rounded overflow-auto max-h-96 text-xs">
						{request.body}
					</pre>
				</Paragraph>
			) : (
				<Empty description="No body" />
			),
		},
		{
			key: "flags",
			label: (
				<span>
					<FlagOutlined /> Flags ({request.flags.length})
				</span>
			),
			children:
				request.flags.length > 0 ? (
					<Table
						columns={flagColumns}
						dataSource={request.flags}
						rowKey="id"
						size="small"
						pagination={false}
					/>
				) : (
					<Empty description="No flags found" />
				),
		},
		{
			key: "links",
			label: (
				<span>
					<LinkOutlined /> Linked ({request.linked_requests.length})
				</span>
			),
			children:
				request.linked_requests.length > 0 ? (
					(() => {
						// Get incoming and outgoing requests
						const incoming = request.linked_requests.filter(
							(r: any) => r.direction === "incoming",
						);
						const outgoing = request.linked_requests.filter(
							(r: any) => r.direction === "outgoing",
						);

						// Take last 5 incoming and first 5 outgoing
						const limitedIncoming = incoming.slice(-5);
						const limitedOutgoing = outgoing.slice(0, 5);

						// Get session key from any linked request
						const sessionKey = request.linked_requests.find(
							(r: any) => r.session_key,
						)?.session_key;
						console.log("Linked requests:", request.linked_requests);
						console.log("Session key found:", sessionKey);

						// Combine all requests for the flow
						const requestFlow = [
							...limitedIncoming,
							{
								id: request.id,
								method: request.method,
								path: request.path,
								time: new Date(request.timestamp).toLocaleTimeString("en-US", {
									hour12: false,
								}),
								direction: "current",
							},
							...limitedOutgoing,
						];

						const flowColumns = [
							{
								title: "ID",
								dataIndex: "id",
								key: "id",
								width: 80,
							},
							{
								title: "Method",
								dataIndex: "method",
								key: "method",
								width: 80,
								render: (method: string) => <Tag>{method}</Tag>,
							},
							{
								title: "Path",
								dataIndex: "path",
								key: "path",
							},
							{
								title: "Time",
								dataIndex: "time",
								key: "time",
								width: 100,
							},
							{
								title: "Action",
								key: "action",
								width: 80,
								render: (_: any, record: any) => {
									if (record.direction === "current") {
										return <Text type="secondary">Current</Text>;
									}
									return (
										<Button
											type="link"
											size="small"
											icon={<LinkOutlined />}
											onClick={() =>
												navigate({
													to: `/service/${port}/request/${record.id}`,
												})
											}
										>
											View
										</Button>
									);
								},
							},
						];

						return (
							<>
								{sessionKey && (
									<div className="mb-2">
										<Text type="secondary">Session: </Text>
										<Text code className="text-xs">
											{sessionKey}
										</Text>
									</div>
								)}
								<Table
									columns={flowColumns}
									dataSource={requestFlow}
									rowKey="id"
									size="small"
									pagination={false}
									rowClassName={(record) =>
										record.direction === "current" ? "bg-blue-50 font-bold" : ""
									}
								/>
								{(incoming.length > 5 || outgoing.length > 5) && (
									<div className="mt-2 text-center">
										<Text type="secondary" className="text-xs">
											Showing {limitedIncoming.length} of {incoming.length}{" "}
											previous requests and {limitedOutgoing.length} of{" "}
											{outgoing.length} following requests
										</Text>
									</div>
								)}
							</>
						);
					})()
				) : (
					<Empty description="No linked requests" />
				),
		},
	];

	const responseTabItems = response
		? [
				{
					key: "headers",
					label: `Headers (${response.headers.length})`,
					children:
						response.headers.length > 0 ? (
							<Table
								columns={headerColumns}
								dataSource={response.headers}
								rowKey="name"
								size="small"
								pagination={false}
							/>
						) : (
							<Empty description="No headers" />
						),
				},
				{
					key: "body",
					label: "Body",
					children: response.body ? (
						<Paragraph>
							<pre className="bg-gray-100 p-2 rounded overflow-auto max-h-96 text-xs">
								{response.body}
							</pre>
						</Paragraph>
					) : (
						<Empty description="No body" />
					),
				},
				{
					key: "flags",
					label: (
						<span>
							<FlagOutlined /> Flags ({response.flags.length})
						</span>
					),
					children:
						response.flags.length > 0 ? (
							<Table
								columns={flagColumns}
								dataSource={response.flags}
								rowKey="id"
								size="small"
								pagination={false}
							/>
						) : (
							<Empty description="No flags found" />
						),
				},
			]
		: [];

	const handleViewRaw = async () => {
		const result = await fetchRawData();
		if (result.data) {
			setRawModalVisible(true);
		} else {
			message.error("Failed to load raw request data");
		}
	};

	const controls = (
		<Button
			icon={<CodeOutlined />}
			onClick={handleViewRaw}
			loading={loadingRawData}
		>
			View Raw
		</Button>
	);

	const pageActionsContainer = document.getElementById("page-actions");

	return (
		<div className="space-y-4">
			{pageActionsContainer && createPortal(controls, pageActionsContainer)}

			<Modal
				title="Raw Request Data"
				open={rawModalVisible}
				onCancel={() => setRawModalVisible(false)}
				footer={null}
				width={800}
			>
				{rawData && (
					<pre className="bg-gray-100 p-4 rounded overflow-auto max-h-96 text-xs">
						{JSON.stringify(rawData, null, 2)}
					</pre>
				)}
			</Modal>

			<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
				<Card
					title={`${request.method} ${request.path}`}
					size="small"
					bodyStyle={{ padding: "8px" }}
				>
					<Tabs items={requestTabItems} size="small" />
				</Card>

				<Card
					title={
						response ? (
							<>
								Response{" "}
								<Tag
									color={
										response.status &&
										response.status >= 200 &&
										response.status < 300
											? "success"
											: response.status &&
													response.status >= 300 &&
													response.status < 400
												? "processing"
												: response.status &&
														response.status >= 400 &&
														response.status < 500
													? "warning"
													: response.status && response.status >= 500
														? "error"
														: "default"
									}
								>
									{response.status || "N/A"}
								</Tag>
							</>
						) : (
							"Response"
						)
					}
					size="small"
					bodyStyle={{ padding: "8px" }}
				>
					{response ? (
						<Tabs items={responseTabItems} size="small" />
					) : (
						<Empty description="No response received" />
					)}
				</Card>
			</div>
		</div>
	);
}
