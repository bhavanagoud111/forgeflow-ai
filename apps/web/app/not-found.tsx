import Link from "next/link";
import { EmptyState } from "@/components/common/states";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <EmptyState title="Page not found" description="The page you are looking for does not exist." className="mt-12">
      <Button asChild variant="secondary" size="sm" className="mt-2">
        <Link href="/">Back to dashboard</Link>
      </Button>
    </EmptyState>
  );
}
