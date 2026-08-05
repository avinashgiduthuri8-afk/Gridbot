import { Route, Switch } from "wouter";
import { Layout } from "@/components/Layout";
import DashboardHome from "@/pages/DashboardHome";
import LiveGrids from "@/pages/LiveGrids";
import Positions from "@/pages/Positions";
import Orders from "@/pages/Orders";
import TradeHistory from "@/pages/TradeHistory";
import Portfolio from "@/pages/Portfolio";
import Analytics from "@/pages/Analytics";
import SettingsPage from "@/pages/Settings";
import NotFound from "@/pages/NotFound";

export default function App() {
  return (
    <Layout>
      <Switch>
        <Route path="/" component={DashboardHome} />
        <Route path="/grids" component={LiveGrids} />
        <Route path="/positions" component={Positions} />
        <Route path="/orders" component={Orders} />
        <Route path="/trade-history" component={TradeHistory} />
        <Route path="/portfolio" component={Portfolio} />
        <Route path="/analytics" component={Analytics} />
        <Route path="/settings" component={SettingsPage} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}
