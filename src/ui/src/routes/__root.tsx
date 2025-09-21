import {
	Outlet,
	createRootRouteWithContext,
	useNavigate,
	useLocation,
} from "@tanstack/react-router";
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools";
import { TanstackDevtools } from "@tanstack/react-devtools";

import TanStackQueryDevtools from "../integrations/tanstack-query/devtools";

import type { QueryClient } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { getServicesApiServicesGetOptions } from "@/client/@tanstack/react-query.gen";

import { Breadcrumb, Layout, Menu, theme, Spin } from "antd";
import { DashboardOutlined, ApiOutlined } from "@ant-design/icons";
import { useHealthCheck } from "@/hooks/useHealthCheck";
import { HostConfig } from "@/components/HostConfig";

const { Header, Content, Footer } = Layout;

interface MyRouterContext {
	queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<MyRouterContext>()({
	component: () => {
		const {
			token: { colorBgContainer, borderRadiusLG },
		} = theme.useToken();
		const navigate = useNavigate();
		const location = useLocation();
		const { isHealthy, isChecking, error, apiUrl } = useHealthCheck();

		const { data } = useQuery({
			...getServicesApiServicesGetOptions(),
			enabled: isHealthy, // Only query if healthy
			refetchInterval: 30000, // Refresh every 30 seconds
		});

		// Determine selected key based on current path
		const getSelectedKey = () => {
			const path = location.pathname;
			if (path === "/") {
				return "dashboard";
			}
			const serviceMatch = path.match(/^\/service\/(\d+)/);
			if (serviceMatch) {
				return `service-${serviceMatch[1]}`;
			}
			return "dashboard";
		};

		const menuItems = [
			{
				key: "dashboard",
				label: "Dashboard",
				icon: <DashboardOutlined />,
				onClick: () => navigate({ to: "/" }),
			},
			...(data?.services?.map((service) => ({
				key: `service-${service.port}`,
				label: `${service.name.substring(0, 4).toUpperCase()}:${service.port}`,
				icon: <ApiOutlined />,
				onClick: () => navigate({ to: `/service/${service.port}` }),
			})) || []),
		];

		// Build breadcrumbs based on current path
		const getBreadcrumbs = () => {
			const path = location.pathname;
			const items = [{ title: "Dashboard", href: "/" }];

			const serviceMatch = path.match(/^\/service\/(\d+)/);
			if (serviceMatch) {
				const port = serviceMatch[1];
				const service = data?.services?.find((s) => s.port === parseInt(port));
				if (service) {
					items.push({
						title: `${service.name.substring(0, 4).toUpperCase()}:${service.port}`,
						href: `/service/${port}`,
					});

					// Check for sub-routes
					if (path.includes("/paths")) {
						items.push({ title: "Path Stats" });
					} else if (path.includes("/queries")) {
						items.push({ title: "Query Stats" });
					} else if (path.includes("/headers")) {
						items.push({ title: "Header Stats" });
					} else if (path.includes("/request/")) {
						const requestMatch = path.match(/\/request\/(\d+)/);
						if (requestMatch) {
							const requestId = requestMatch[1];
							items.push({ title: `Request #${requestId}` });
						}
					}
				}
			}

			return items;
		};

		if (isChecking) {
			return (
				<div
					style={{
						height: "100vh",
						display: "flex",
						alignItems: "center",
						justifyContent: "center",
					}}
				>
					<Spin size="large" tip="Checking server connection..." />
				</div>
			);
		}

		if (!isHealthy) {
			return <HostConfig visible={true} currentUrl={apiUrl} error={error} />;
		}

		return (
			<>
				<Layout style={{ minHeight: "100vh" }}>
					<Header style={{ display: "flex", alignItems: "center" }}>
						<div className="demo-logo" />
						<Menu
							theme="dark"
							mode="horizontal"
							selectedKeys={[getSelectedKey()]}
							items={menuItems}
							style={{ flex: 1, minWidth: 0 }}
						/>
					</Header>
					<Content style={{ padding: "0 48px" }}>
						<div
							style={{
								margin: "16px 0",
								display: "flex",
								justifyContent: "space-between",
								alignItems: "center",
								minHeight: "32px",
							}}
						>
							<Breadcrumb
								items={getBreadcrumbs()}
								itemRender={(item, _, items) => {
									const last = items[items.length - 1];
									if (item === last) {
										return <span>{item.title}</span>;
									}
									return (
										<a onClick={() => item.href && navigate({ to: item.href })}>
											{item.title}
										</a>
									);
								}}
							/>
							<div id="page-actions" style={{ minHeight: "32px" }} />
						</div>
						<div
							style={{
								background: colorBgContainer,
								minHeight: "100%",
								padding: 24,
								borderRadius: borderRadiusLG,
							}}
						>
							<Outlet />
						</div>
					</Content>
					<Footer style={{ textAlign: "center" }}></Footer>
				</Layout>
				<TanstackDevtools
					config={{
						position: "bottom-left",
					}}
					plugins={[
						{
							name: "Tanstack Router",
							render: <TanStackRouterDevtoolsPanel />,
						},
						TanStackQueryDevtools,
					]}
				/>
			</>
		);
	},
});
