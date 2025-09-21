import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getRequestDetailApiRequestsRequestIdGetOptions } from "@/client/@tanstack/react-query.gen";
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
	Timeline,
} from "antd";
import {
	LinkOutlined,
	FlagOutlined,
	ArrowRightOutlined,
	ArrowLeftOutlined,
	ClockCircleOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";

const { Text, Paragraph } = Typography;

export const Route = createFileRoute("/service/$port/request/$id")({
	component: RequestDetail,
});

function RequestDetail() {
	const { id, port } = Route.useParams();
	const requestId = parseInt(id);
	const navigate = useNavigate();

	const { data, isLoading, error } = useQuery({
		...getRequestDetailApiRequestsRequestIdGetOptions({
			path: { request_id: requestId },
		}),
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
			title: "Reason",
			dataIndex: "reason",
			key: "reason",
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
					<Descriptions.Item label="Port">{request.port}</Descriptions.Item>
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
					<div className="space-y-4">
						{/* Request Flow Timeline */}
						<Card size="small" title="Request Flow" bordered={false}>
							<Timeline mode="alternate">
								{request.linked_requests
									.filter((r: any) => r.direction === "incoming")
									.map((r: any) => (
										<Timeline.Item
											key={`in-${r.id}`}
											color="blue"
											dot={<ArrowRightOutlined style={{ fontSize: "16px" }} />}
										>
											<div
												className="cursor-pointer hover:bg-gray-50 p-2 rounded"
												onClick={() =>
													navigate({ to: `/service/${port}/request/${r.id}` })
												}
											>
												<Text strong>
													{r.method} {r.path}
												</Text>
												<br />
												<Text type="secondary" className="text-xs">
													Request #{r.id} at {r.time}
												</Text>
											</div>
										</Timeline.Item>
									))}

								<Timeline.Item
									color="green"
									dot={<ClockCircleOutlined style={{ fontSize: "16px" }} />}
								>
									<div className="bg-green-50 p-2 rounded">
										<Text strong>Current Request #{request.id}</Text>
										<br />
										<Text>
											{request.method} {request.path}
										</Text>
									</div>
								</Timeline.Item>

								{request.linked_requests
									.filter((r: any) => r.direction === "outgoing")
									.map((r: any) => (
										<Timeline.Item
											key={`out-${r.id}`}
											color="orange"
											dot={<ArrowRightOutlined style={{ fontSize: "16px" }} />}
										>
											<div
												className="cursor-pointer hover:bg-gray-50 p-2 rounded"
												onClick={() =>
													navigate({ to: `/service/${port}/request/${r.id}` })
												}
											>
												<Text strong>
													{r.method} {r.path}
												</Text>
												<br />
												<Text type="secondary" className="text-xs">
													Request #{r.id} at {r.time}
												</Text>
											</div>
										</Timeline.Item>
									))}
							</Timeline>
						</Card>

						{/* Detailed Table */}
						<Card size="small" title="Linked Requests Details" bordered={false}>
							<Table
								columns={linkedRequestColumns}
								dataSource={request.linked_requests}
								rowKey="id"
								size="small"
								pagination={false}
							/>
						</Card>
					</div>
				) : (
					<Empty description="No linked requests" />
				),
		},
	];

	const responseTabItems = response
		? [
				{
					key: "info",
					label: "Info",
					children: (
						<Descriptions column={1} size="small">
							<Descriptions.Item label="Status">
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
							</Descriptions.Item>
						</Descriptions>
					),
				},
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

	return (
		<div className="space-y-4">
			<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
				<Card title="📤 Request" size="small" bodyStyle={{ padding: "8px" }}>
					<Tabs items={requestTabItems} size="small" />
				</Card>

				<Card title="📥 Response" size="small" bodyStyle={{ padding: "8px" }}>
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
