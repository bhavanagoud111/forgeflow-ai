import type { Metadata } from "next";
import { RepositoryDetailView } from "@/components/repositories/repository-detail";

export const metadata: Metadata = { title: "Repository" };

export default async function RepositoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RepositoryDetailView key={id} id={decodeURIComponent(id)} />;
}
