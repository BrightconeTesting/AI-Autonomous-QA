import { AppRegistrationForm } from "@/components/AppRegistrationForm";

export default function NewAppPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Register application</h1>
      <AppRegistrationForm />
    </div>
  );
}
