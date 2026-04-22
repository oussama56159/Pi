import Card, { CardHeader, CardTitle, CardContent } from '@/components/ui/Card';

export default function PlantsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Plants</h1>
        <p className="text-sm text-slate-400 mt-1">Plant tracking and capture workflows.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle subtitle="This section is not yet implemented in the dashboard UI">Coming soon</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-400">
            The backend services can run without this page, but the route exists in the navigation.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
